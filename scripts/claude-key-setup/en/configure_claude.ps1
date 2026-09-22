# Claude Code API key setup (Windows PowerShell)
# Run directly with .\configure_claude.ps1

param(
    [Alias("c")]
    [ValidateScript({ -not [string]::IsNullOrWhiteSpace($_) })]
    [string]$ConfigPath
)

# Colored output helpers
function Write-Info($message) { Write-Host $message -ForegroundColor Blue }
function Write-Success($message) { Write-Host $message -ForegroundColor Green }
function Write-Warn($message) { Write-Host $message -ForegroundColor Yellow }
function Write-ErrorMsg($message) { Write-Host $message -ForegroundColor Red }

# Check prerequisites
function Check-Prerequisites {
    $all_ok = $true

    Write-Host "Checking prerequisites..." -ForegroundColor Cyan
    Write-Host ""

    if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSVersion -lt [version]'5.1') {
        Write-ErrorMsg "Run this script in Windows PowerShell 5.1 or PowerShell 7 on Windows."
        exit 1
    }

    # 1. Check the PowerShell version
    $psVersion = $PSVersionTable.PSVersion.ToString()
    Write-Host "  PowerShell: $psVersion" -ForegroundColor Green

    # 2. Check for a Claude Code configuration file
    $config_found = $false
    $config_paths = @(
        "$HOME\.claude\settings.json",
        "$HOME\.claude\settings.local.json"
    )

    foreach ($cfg in $config_paths) {
        if (Test-Path $cfg) {
            Write-Host "  Claude configuration: $cfg" -ForegroundColor Green
            $config_found = $true
            break
        }
    }

    if (-not $config_found) {
        Write-Host "  Claude configuration: Not found" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Note:" -ForegroundColor Blue
        Write-Host "    - This is expected if you have not run Claude Code yet."
        Write-Host "    - The script will create a configuration file during setup."
    }

    Write-Host ""

    if (-not $all_ok) {
        Write-Host "Prerequisite checks failed. Resolve the issues above and try again." -ForegroundColor Red
        exit 1
    }

    Write-Host "All required checks passed!" -ForegroundColor Green
    Write-Host ""
}

# Find the configuration file
function Find-ConfigFile {
    param([string]$CustomConfig)

    # Always use an explicitly supplied configuration path
    if (-not [string]::IsNullOrWhiteSpace($CustomConfig)) {
        return $CustomConfig
    }

    # Check common locations
    $candidates = @(
        "$HOME\.claude\settings.json",
        "$HOME\.claude\settings.local.json"
    )

    foreach ($cfg in $candidates) {
        if (Test-Path $cfg) {
            return $cfg
        }
    }

    # Default to settings.json
    return "$HOME\.claude\settings.json"
}

# Accept only regular files; check before creating backups, temporary files, or directories.
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
        throw "The configuration file is a symbolic link or reparse point. Specify the actual target file."
    }
    if (($attributes -band [System.IO.FileAttributes]::Directory) -ne 0) {
        throw "The configuration path must refer to a file."
    }
    return $true
}

# Create files accessible only to the current user and SYSTEM, without inheriting parent permissions.
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
        throw "The file system did not apply the private ACL. The write has been canceled."
    }
    $rules = $Security.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
    foreach ($rule in $rules) {
        $sid = $rule.IdentityReference.Value
        if ($rule.IsInherited -or $sid -notin $allowedSids -or
            $rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow -or
            $rule.FileSystemRights -ne [System.Security.AccessControl.FileSystemRights]::FullControl) {
            throw "The file system did not apply the expected private ACL. The write has been canceled."
        }
        $seenSids[$sid] = $true
    }
    foreach ($sid in $allowedSids) {
        if (-not $seenSids.ContainsKey($sid)) {
            throw "The file system did not apply the complete private ACL. The write has been canceled."
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
        # Write credentials only after verifying the ACL.
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

# Check nesting depth first because PowerShell 5.1 does not warn when JSON serialization truncates data.
function Assert-JsonDepth {
    param($Value, [int]$Depth = 0)

    if ($null -eq $Value) { return }
    if ($Value -is [DateTime] -or $Value -is [DateTimeOffset]) {
        throw "This PowerShell version converts date strings and cannot safely preserve the configuration. The update has been canceled."
    }
    if ($Value -is [System.Collections.IDictionary]) {
        if ($Depth -gt 100) { throw "The configuration exceeds the supported nesting depth of 100. The update has been canceled." }
        foreach ($key in $Value.Keys) {
            Assert-JsonDepth -Value $Value[$key] -Depth ($Depth + 1)
        }
    } elseif ($Value -is [System.Management.Automation.PSCustomObject]) {
        if ($Depth -gt 100) { throw "The configuration exceeds the supported nesting depth of 100. The update has been canceled." }
        foreach ($property in $Value.PSObject.Properties) {
            Assert-JsonDepth -Value $property.Value -Depth ($Depth + 1)
        }
    } elseif ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        if ($Depth -gt 100) { throw "The configuration exceeds the supported nesting depth of 100. The update has been canceled." }
        foreach ($item in $Value) {
            Assert-JsonDepth -Value $item -Depth ($Depth + 1)
        }
    }
}

function Publish-ConfigFile {
    param([string]$TempFile, [string]$ConfigFile, [bool]$ReplaceExisting)

    if ($ReplaceExisting) {
        # Pass a true null to the .NET string parameter; $null becomes an empty path.
        [System.IO.File]::Replace($TempFile, $ConfigFile, [System.Management.Automation.Language.NullString]::Value)
    } else {
        [System.IO.File]::Move($TempFile, $ConfigFile)
    }
}

function Update-ConfigFile {
    param([string]$ConfigFile, [string]$BaseUrl, [string]$ApiKey, [string]$ModelName)

    # Resolve relative filenames to full paths to avoid empty parent paths and wildcard expansion.
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
                throw "The configuration file must contain a JSON object. The update has been canceled."
            }
            $jsonOptions = @{ InputObject = $configText; ErrorAction = 'Stop' }
            if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) {
                $jsonOptions.DateKind = 'String'
            }
            $newConfig = ConvertFrom-Json @jsonOptions
            if ($newConfig -isnot [System.Management.Automation.PSCustomObject]) {
                throw "The configuration file must contain a JSON object. The update has been canceled."
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

        # Check again before writing; do not create an empty configuration file beforehand.
        if ((Test-ConfigFile -Path $fullPath) -ne $exists) {
            throw "The configuration file state has changed. Run the script again."
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
        # Clean up only temporary files created by this run; never remove existing files after a CreateNew conflict.
        $tempFile = $tempCandidate

        if ($exists) {
            if (-not (Test-ConfigFile -Path $fullPath)) { throw "The original configuration file has been moved." }
            # File.Replace preserves the destination DACL, so restrict it before publishing new credentials.
            # If permission updates fail, preserve the original file; leave parent and historical backup permissions unchanged.
            Set-Acl -LiteralPath $fullPath -AclObject (New-PrivateFileSecurity) -ErrorAction Stop
            Assert-PrivateFileSecurity -Security (Get-Acl -LiteralPath $fullPath -ErrorAction Stop)
            try {
                Publish-ConfigFile -TempFile $tempFile -ConfigFile $fullPath -ReplaceExisting $true
            } catch {
                # Some Windows ReplaceFile failures remove the original destination; attempt recovery only if it is missing.
                # Recover with a private file and a non-overwriting rename, preserving concurrent files and the private backup.
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
            # Rename the complete private file within the same directory; fail if the destination already exists.
            Publish-ConfigFile -TempFile $tempFile -ConfigFile $fullPath -ReplaceExisting $false
        }
        $tempFile = $null
        return $backupFile
    } catch {
        # Return only a safe error message and the path of any backup completed during this run.
        $failure = [System.InvalidOperationException]::new("The configuration update did not complete.")
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

# 1. Checking prerequisites
Check-Prerequisites

# 2. Select the configuration file (supports -c / -ConfigPath)
$CONFIG_FILE = Find-ConfigFile -CustomConfig $ConfigPath

try {
    $CONFIG_FILE = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($CONFIG_FILE)
    if (-not (Test-ConfigFile -Path $CONFIG_FILE)) {
        Write-Host "No configuration file found. A new file will be created after you enter the settings." -ForegroundColor Yellow
    }
} catch {
    Write-ErrorMsg "The configuration path is invalid, inaccessible, or a symbolic link / reparse point. Use -ConfigPath to specify a regular file."
    exit 1
}

Write-Host "Using configuration file: $CONFIG_FILE"
Write-Host ""

# 3. Show the menu
Write-Host "=========================================="
Write-Host "  Claude Code Setup - StepFun"
Write-Host "=========================================="
Write-Host ""
Write-Host "Get an API key:"
Write-Host "  StepFun: https://platform.stepfun.ai/interface-key"
Write-Host ""
Write-Host "Choose a StepFun connection:"
Write-Host "  1) StepFun Official API (pay as you go)"
Write-Host "  2) StepFun Step Plan (subscription)"
Write-Host ""

# 4. Read the selection
do {
    $choice = Read-Host "Enter a number [1-2]"
    if ($choice -notmatch '^[1-2]$') {
        Write-Host "Invalid input. Enter 1 or 2."
    }
} while ($choice -notmatch '^[1-2]$')

Write-Host ""

# 5. Set configuration values for the selected connection
switch ($choice) {
    '1' {
        $PROVIDER = "stepfun-official"
        $PROMPT = "Enter your StepFun API Key"
        $DEFAULT_MODEL = "step-5-preview"
        $BASE_URL = "https://api.stepfun.ai/"
    }
    '2' {
        $PROVIDER = "stepfun-plan"
        $PROMPT = "Enter your StepFun API Key"
        $DEFAULT_MODEL = "step-5-preview"
        $BASE_URL = "https://api.stepfun.ai/step_plan"
    }
}

# 6. Read the API key
do {
    $secureKey = Read-Host -Prompt "${PROMPT} (input hidden)" -AsSecureString
    $keyPointer = [IntPtr]::Zero
    try {
        $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        $API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    } finally {
        if ($keyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
        $secureKey.Dispose()
    }
    if ([string]::IsNullOrWhiteSpace($API_KEY)) {
        Write-Host "The API key cannot be empty. Please try again."
    }
} while ([string]::IsNullOrWhiteSpace($API_KEY))

# 7. Read the model name
$MODEL_NAME = Read-Host "Model name [default: $DEFAULT_MODEL]"
if ([string]::IsNullOrWhiteSpace($MODEL_NAME)) {
    $MODEL_NAME = $DEFAULT_MODEL
}

# 8. Build the complete configuration and create a private backup before replacing only env.
Write-Host ""
Write-Host "Configuring Claude Code..."
try {
    $backup_file = Update-ConfigFile -ConfigFile $CONFIG_FILE -BaseUrl $BASE_URL -ApiKey $API_KEY -ModelName $MODEL_NAME
} catch {
    # Do not print raw exceptions: JSON parse errors may include credentials from the original configuration.
    Write-ErrorMsg "The configuration update did not complete. Check the JSON format, nesting depth, date-string compatibility, and file permissions. Use a file system that supports Windows ACLs."
    if ($_.Exception.Data.Contains('BackupFile')) {
        Write-Warn "A private backup of the original configuration has been retained: $($_.Exception.Data['BackupFile'])"
        Write-Warn "Check that the current configuration is complete and restore it from this backup if needed."
    }
    exit 1
} finally {
    $API_KEY = $null
}

Write-Host "  Claude Code configuration updated" -ForegroundColor Green
Write-Host ""
Write-Host "=========================================="
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "=========================================="
Write-Host ""
Write-Host "Configuration file: $CONFIG_FILE"
if ($backup_file) { Write-Host "Backup file: $backup_file" }
Write-Host ""
Write-Host "Current configuration:"
$providerName = if ($choice -eq '1') { 'StepFun Official API' } else { 'StepFun Step Plan' }
Write-Host "   Provider: $providerName"
Write-Host "   API Key: Configured"
Write-Host "   Endpoint: $BASE_URL"
Write-Host "   Model: $MODEL_NAME"
Write-Host ""
Write-Host "Important: Restart Claude Code to apply the changes." -ForegroundColor Yellow
Write-Host ""

Write-Host "Press any key to exit..."
[void][Console]::ReadKey($true)
