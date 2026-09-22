# Claude Code API Key 配置脚本 (Windows PowerShell 版本)
# 支持：直接运行 .\configure_claude.ps1

param(
    [Alias("c")]
    [ValidateScript({ -not [string]::IsNullOrWhiteSpace($_) })]
    [string]$ConfigPath
)

# 颜色函数
function Write-Info($message) { Write-Host $message -ForegroundColor Blue }
function Write-Success($message) { Write-Host $message -ForegroundColor Green }
function Write-Warn($message) { Write-Host $message -ForegroundColor Yellow }
function Write-ErrorMsg($message) { Write-Host $message -ForegroundColor Red }

# 前置条件检查
function Check-Prerequisites {
    $all_ok = $true

    Write-Host "检查前置条件..." -ForegroundColor Cyan
    Write-Host ""

    if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSVersion -lt [version]'5.1') {
        Write-ErrorMsg "请使用 Windows PowerShell 5.1 或 Windows 上的 PowerShell 7 运行。"
        exit 1
    }

    # 1. 检查 PowerShell 版本
    $psVersion = $PSVersionTable.PSVersion.ToString()
    Write-Host "  PowerShell: $psVersion" -ForegroundColor Green

    # 2. 检查 Claude Code 配置文件
    $config_found = $false
    $config_paths = @(
        "$HOME\.claude\settings.json",
        "$HOME\.claude\settings.local.json"
    )

    foreach ($cfg in $config_paths) {
        if (Test-Path $cfg) {
            Write-Host "  Claude 配置: $cfg" -ForegroundColor Green
            $config_found = $true
            break
        }
    }

    if (-not $config_found) {
        Write-Host "  Claude 配置: 未找到" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  提示：" -ForegroundColor Blue
        Write-Host "    - 如果 Claude Code 未运行过，这是正常的"
        Write-Host "    - 脚本将在配置时创建配置文件"
    }

    Write-Host ""

    if (-not $all_ok) {
        Write-Host "前置条件检查失败，请解决上述问题后重试" -ForegroundColor Red
        exit 1
    }

    Write-Host "所有必需条件检查通过！" -ForegroundColor Green
    Write-Host ""
}

# 查找配置文件
function Find-ConfigFile {
    param([string]$CustomConfig)

    # 如果用户指定了配置，优先使用
    if (-not [string]::IsNullOrWhiteSpace($CustomConfig)) {
        return $CustomConfig
    }

    # 检查常见位置
    $candidates = @(
        "$HOME\.claude\settings.json",
        "$HOME\.claude\settings.local.json"
    )

    foreach ($cfg in $candidates) {
        if (Test-Path $cfg) {
            return $cfg
        }
    }

    # 默认使用 settings.json
    return "$HOME\.claude\settings.json"
}

# 只允许普通文件，且在创建备份、临时文件或目录之前检查。
function Test-ConfigFile {
    param([string]$Path)

    try {
        $attributes = [System.IO.File]::GetAttributes($Path)
    } catch [System.IO.FileNotFoundException] {
        return $false
    } catch [System.IO.DirectoryNotFoundException] {
        return $false
    }
    if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "配置文件是符号链接或重解析点，请指定真实配置文件。"
    }
    if (($attributes -band [System.IO.FileAttributes]::Directory) -ne 0) {
        throw "配置路径必须是文件。"
    }
    return $true
}

# 文件从创建时起即仅允许当前用户和 SYSTEM 访问，不继承父目录权限。
function New-PrivateFileSecurity {
    $security = New-Object System.Security.AccessControl.FileSecurity
    $security.SetAccessRuleProtection($true, $false)
    $userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $systemSid = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')
    foreach ($sid in @($userSid, $systemSid)) {
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $sid, [System.Security.AccessControl.FileSystemRights]::FullControl,
            [System.Security.AccessControl.AccessControlType]::Allow)
        $security.AddAccessRule($rule)
    }
    return $security
}

function Assert-PrivateFileSecurity {
    param([System.Security.AccessControl.FileSecurity]$Security)

    $userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $allowedSids = @($userSid, 'S-1-5-18')
    $seenSids = @{}
    if (-not $Security.AreAccessRulesProtected) {
        throw "文件系统未应用私有 ACL，已取消写入。"
    }
    $rules = $Security.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
    foreach ($rule in $rules) {
        $sid = $rule.IdentityReference.Value
        if ($rule.IsInherited -or $sid -notin $allowedSids -or
            $rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow -or
            $rule.FileSystemRights -ne [System.Security.AccessControl.FileSystemRights]::FullControl) {
            throw "文件系统未应用预期的私有 ACL，已取消写入。"
        }
        $seenSids[$sid] = $true
    }
    foreach ($sid in $allowedSids) {
        if (-not $seenSids.ContainsKey($sid)) {
            throw "文件系统未应用完整的私有 ACL，已取消写入。"
        }
    }
}

function Write-PrivateFile {
    param([string]$Path, [byte[]]$Bytes)

    $stream = $null
    $created = $false
    $complete = $false
    try {
        $security = New-PrivateFileSecurity
        if ($PSVersionTable.PSEdition -eq 'Desktop') {
            $stream = [System.IO.FileStream]::new($Path, [System.IO.FileMode]::CreateNew,
                [System.Security.AccessControl.FileSystemRights]::FullControl,
                [System.IO.FileShare]::None, 4096, [System.IO.FileOptions]::None, $security)
        } else {
            $stream = [System.IO.FileSystemAclExtensions]::Create([System.IO.FileInfo]::new($Path),
                [System.IO.FileMode]::CreateNew, [System.Security.AccessControl.FileSystemRights]::FullControl,
                [System.IO.FileShare]::None, 4096, [System.IO.FileOptions]::None, $security)
        }
        $created = $true
        if ($PSVersionTable.PSEdition -eq 'Desktop') {
            Assert-PrivateFileSecurity -Security $stream.GetAccessControl()
        } else {
            Assert-PrivateFileSecurity -Security ([System.IO.FileSystemAclExtensions]::GetAccessControl($stream))
        }
        # ACL 验证成功后才向文件写入凭据。
        $stream.Write($Bytes, 0, $Bytes.Length)
        $stream.Flush($true)
        $complete = $true
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if ($created -and -not $complete) {
            Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        }
    }
}

# PowerShell 5.1 不会对 JSON 序列化截断发出警告，因此先检查嵌套深度。
function Assert-JsonDepth {
    param($Value, [int]$Depth = 0)

    if ($null -eq $Value) { return }
    if ($Value -is [DateTime] -or $Value -is [DateTimeOffset]) {
        throw "当前 PowerShell 会转换日期字符串，无法安全保留原配置，已取消更新。"
    }
    if ($Value -is [System.Collections.IDictionary]) {
        if ($Depth -gt 100) { throw "配置嵌套超过支持的 100 层，已取消更新。" }
        foreach ($key in $Value.Keys) {
            Assert-JsonDepth -Value $Value[$key] -Depth ($Depth + 1)
        }
    } elseif ($Value -is [System.Management.Automation.PSCustomObject]) {
        if ($Depth -gt 100) { throw "配置嵌套超过支持的 100 层，已取消更新。" }
        foreach ($property in $Value.PSObject.Properties) {
            Assert-JsonDepth -Value $property.Value -Depth ($Depth + 1)
        }
    } elseif ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        if ($Depth -gt 100) { throw "配置嵌套超过支持的 100 层，已取消更新。" }
        foreach ($item in $Value) {
            Assert-JsonDepth -Value $item -Depth ($Depth + 1)
        }
    }
}

function Publish-ConfigFile {
    param([string]$TempFile, [string]$ConfigFile, [bool]$ReplaceExisting)

    if ($ReplaceExisting) {
        # 向 .NET string 参数传递真正的 null，避免 $null 被转换为空路径。
        [System.IO.File]::Replace($TempFile, $ConfigFile, [System.Management.Automation.Language.NullString]::Value)
    } else {
        [System.IO.File]::Move($TempFile, $ConfigFile)
    }
}

function Update-ConfigFile {
    param([string]$ConfigFile, [string]$BaseUrl, [string]$ApiKey, [string]$ModelName)

    # 将裸相对文件名解析为完整路径，避免空的父目录和通配符解释。
    $fullPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ConfigFile)
    $exists = Test-ConfigFile -Path $fullPath
    $backupFile = $null
    $tempFile = $null
    $recoveryFile = $null
    try {
        if ($exists) {
            $originalBytes = [System.IO.File]::ReadAllBytes($fullPath)
            $configText = [System.Text.UTF8Encoding]::new($false, $true).GetString($originalBytes).TrimStart([char]0xFEFF)
            if ([string]::IsNullOrWhiteSpace($configText) -or -not $configText.TrimStart().StartsWith('{')) {
                throw "配置文件必须是 JSON 对象，已取消更新。"
            }
            $jsonOptions = @{ InputObject = $configText; ErrorAction = 'Stop' }
            if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) {
                $jsonOptions.DateKind = 'String'
            }
            $newConfig = ConvertFrom-Json @jsonOptions
            if ($newConfig -isnot [System.Management.Automation.PSCustomObject]) {
                throw "配置文件必须是 JSON 对象，已取消更新。"
            }
        } else {
            $newConfig = [pscustomobject]@{}
        }
        $newEnv = [ordered]@{
            ANTHROPIC_BASE_URL = $BaseUrl
            ANTHROPIC_AUTH_TOKEN = $ApiKey
            ANTHROPIC_MODEL = $ModelName
            ANTHROPIC_SMALL_FAST_MODEL = $ModelName
            ANTHROPIC_DEFAULT_SONNET_MODEL = $ModelName
            ANTHROPIC_DEFAULT_OPUS_MODEL = $ModelName
            ANTHROPIC_DEFAULT_HAIKU_MODEL = $ModelName
        }
        $newConfig | Add-Member -MemberType NoteProperty -Name env -Value $newEnv -Force -ErrorAction Stop
        Assert-JsonDepth -Value $newConfig
        $updatedJson = ConvertTo-Json -InputObject $newConfig -Depth 100 -WarningAction Stop -ErrorAction Stop
        $utf8 = [System.Text.UTF8Encoding]::new($true)
        [byte[]]$updatedBytes = $utf8.GetPreamble() + $utf8.GetBytes($updatedJson + [Environment]::NewLine)

        # 再次检查后才开始写入；不提前创建空配置文件。
        if ((Test-ConfigFile -Path $fullPath) -ne $exists) {
            throw "配置文件状态已变化，请重新运行。"
        }
        $directory = [System.IO.Path]::GetDirectoryName($fullPath)
        [System.IO.Directory]::CreateDirectory($directory) | Out-Null
        if ($exists) {
            $backupCandidate = "$fullPath.bak.$(Get-Date -Format 'yyyyMMddHHmmss').$([Guid]::NewGuid().ToString('N'))"
            Write-PrivateFile -Path $backupCandidate -Bytes $originalBytes
            $backupFile = $backupCandidate
        }
        $tempCandidate = "$fullPath.tmp.$([Guid]::NewGuid().ToString('N'))"
        Write-PrivateFile -Path $tempCandidate -Bytes $updatedBytes
        # 仅清理由本次成功创建的临时文件，CreateNew 冲突时不删除已有文件。
        $tempFile = $tempCandidate

        if ($exists) {
            if (-not (Test-ConfigFile -Path $fullPath)) { throw "原配置文件已被移走。" }
            # File.Replace 保留目标 DACL，因此必须在发布新凭据前收紧目标权限。
            # 权限设置失败时不替换原配置，也不修改父目录或历史备份的权限。
            Set-Acl -LiteralPath $fullPath -AclObject (New-PrivateFileSecurity) -ErrorAction Stop
            Assert-PrivateFileSecurity -Security (Get-Acl -LiteralPath $fullPath -ErrorAction Stop)
            try {
                Publish-ConfigFile -TempFile $tempFile -ConfigFile $fullPath -ReplaceExisting $true
            } catch {
                # Windows ReplaceFile 的某些失败会移走原目标；只在目标缺失时尝试恢复。
                # 恢复仍使用私有文件和不覆盖的重命名，保留并发创建的目标及安全备份。
                if (-not (Test-ConfigFile -Path $fullPath)) {
                    $recoveryCandidate = "$fullPath.restore.$([Guid]::NewGuid().ToString('N'))"
                    Write-PrivateFile -Path $recoveryCandidate -Bytes $originalBytes
                    $recoveryFile = $recoveryCandidate
                    [System.IO.File]::Move($recoveryFile, $fullPath)
                    $recoveryFile = $null
                }
                throw
            }
        } else {
            # 同目录重命名完整的私有文件，目标若已被创建则失败，不覆盖它。
            Publish-ConfigFile -TempFile $tempFile -ConfigFile $fullPath -ReplaceExisting $false
        }
        $tempFile = $null
        return $backupFile
    } catch {
        # 只向调用方传递安全的错误说明和本次已完成的备份路径。
        $failure = [System.InvalidOperationException]::new("更新配置未完成。")
        if ($backupFile) { $failure.Data['BackupFile'] = $backupFile }
        throw $failure
    } finally {
        foreach ($privateTemp in @($tempFile, $recoveryFile)) {
            if ($privateTemp -and (Test-Path -LiteralPath $privateTemp)) {
                Remove-Item -LiteralPath $privateTemp -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

# === MAIN ===

# 1. 检查前置条件
Check-Prerequisites

# 2. 确定配置文件（支持 -c / -ConfigPath 参数）
$CONFIG_FILE = Find-ConfigFile -CustomConfig $ConfigPath

try {
    $CONFIG_FILE = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($CONFIG_FILE)
    if (-not (Test-ConfigFile -Path $CONFIG_FILE)) {
        Write-Host "配置文件不存在，将在输入完成后创建" -ForegroundColor Yellow
    }
} catch {
    Write-ErrorMsg "配置路径无效、无权访问，或是符号链接 / 重解析点。请通过 -ConfigPath 指定普通文件路径。"
    exit 1
}

Write-Host "使用配置文件: $CONFIG_FILE"
Write-Host ""

# 3. 菜单
Write-Host "=========================================="
Write-Host "  Claude Code 配置 - 设置 StepFun"
Write-Host "=========================================="
Write-Host ""
Write-Host "获取 API Key："
Write-Host "  StepFun: https://platform.stepfun.com/interface-key"
Write-Host ""
Write-Host "请选择 StepFun 接入方式："
Write-Host "  1) StepFun 官方 API（按量计费）"
Write-Host "  2) StepFun Step Plan（订阅制）"
Write-Host ""

# 4. 读取选择
do {
    $choice = Read-Host "请输入数字 [1-2]"
    if ($choice -notmatch '^[1-2]$') {
        Write-Host "无效输入，请输入 1 或 2"
    }
} while ($choice -notmatch '^[1-2]$')

Write-Host ""

# 5. 根据选择获取配置信息
switch ($choice) {
    '1' {
        $PROVIDER = "stepfun-official"
        $PROMPT = "请输入 StepFun API Key"
        $DEFAULT_MODEL = "step-5-preview"
        $BASE_URL = "https://api.stepfun.com"
    }
    '2' {
        $PROVIDER = "stepfun-plan"
        $PROMPT = "请输入 StepFun API Key"
        $DEFAULT_MODEL = "step-5-preview"
        $BASE_URL = "https://api.stepfun.com/step_plan"
    }
}

# 6. 读取 API Key
do {
    $secureKey = Read-Host -Prompt "${PROMPT}（输入已隐藏）" -AsSecureString
    $keyPointer = [IntPtr]::Zero
    try {
        $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        $API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    } finally {
        if ($keyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
        $secureKey.Dispose()
    }
    if ([string]::IsNullOrWhiteSpace($API_KEY)) {
        Write-Host "API Key 不能为空，请重新输入"
    }
} while ([string]::IsNullOrWhiteSpace($API_KEY))

# 7. 读取模型名称
$MODEL_NAME = Read-Host "模型名称 [默认: $DEFAULT_MODEL]"
if ([string]::IsNullOrWhiteSpace($MODEL_NAME)) {
    $MODEL_NAME = $DEFAULT_MODEL
}

# 8. 完整生成新配置，创建私有备份后只替换 env。
Write-Host ""
Write-Host "正在配置 Claude Code..."
try {
    $backup_file = Update-ConfigFile -ConfigFile $CONFIG_FILE -BaseUrl $BASE_URL -ApiKey $API_KEY -ModelName $MODEL_NAME
} catch {
    # 不打印原始异常，JSON 解析错误可能包含旧配置中的凭据。
    Write-ErrorMsg "更新配置未完成。请检查 JSON 格式、嵌套深度、日期字符串兼容性及文件权限，并使用支持 Windows ACL 的文件系统。"
    if ($_.Exception.Data.Contains('BackupFile')) {
        Write-Warn "原配置的私有备份已保留: $($_.Exception.Data['BackupFile'])"
        Write-Warn "请检查当前配置是否完整，必要时从此备份恢复。"
    }
    exit 1
} finally {
    $API_KEY = $null
}

Write-Host "  Claude Code 配置已更新" -ForegroundColor Green
Write-Host ""
Write-Host "=========================================="
Write-Host "配置完成！" -ForegroundColor Green
Write-Host "=========================================="
Write-Host ""
Write-Host "配置文件: $CONFIG_FILE"
if ($backup_file) { Write-Host "备份文件: $backup_file" }
Write-Host ""
Write-Host "当前配置："
$providerName = if ($choice -eq '1') { 'StepFun 官方 API' } else { 'StepFun Step Plan' }
Write-Host "   提供商: $providerName"
Write-Host "   API Key: 已配置"
Write-Host "   端点: $BASE_URL"
Write-Host "   模型: $MODEL_NAME"
Write-Host ""
Write-Host "重要：请重启 Claude Code 使配置生效" -ForegroundColor Yellow
Write-Host ""

Write-Host "按任意键退出..."
[void][Console]::ReadKey($true)
