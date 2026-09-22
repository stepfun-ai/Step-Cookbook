#!/bin/bash

# Claude Code API key setup for StepFun
# Supports interactive use with curl ... | bash
# Automatically detects the Claude Code configuration file

# Disable tracing before reading credentials, even when launched with bash -x.
set +x
set -e
set -o pipefail
umask 077

# Clean up temporary files
CONFIG_TMP=""
BACKUP_TMP=""
cleanup() {
    unset API_KEY
    if [ -n "$CONFIG_TMP" ]; then rm -f -- "$CONFIG_TMP"; fi
    if [ -n "$BACKUP_TMP" ]; then rm -f -- "$BACKUP_TMP"; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Terminal colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check prerequisites
check_prerequisites() {
    local all_ok=true

    echo "🔍 Checking prerequisites..."
    echo ""

    # 1. Check Bash
    if [ -n "$BASH_VERSION" ]; then
        echo -e "  ✅ bash: $BASH_VERSION"
    else
        echo -e "  ${RED}❌ bash: This script is not running in Bash${NC}"
        all_ok=false
    fi

    # 2. Check the JSON processor so existing settings can be preserved
    if command -v jq >/dev/null 2>&1; then
        echo -e "  ✅ jq: $(jq --version)"
    else
        echo -e "  ${RED}❌ jq: Not installed. Install jq and run this script again.${NC}"
        all_ok=false
    fi

    # 3. Check for a Claude Code configuration file (optional)
    local config_found=false
    local config_paths=(
        "$HOME/.claude/settings.json"
        "$HOME/.claude/settings.local.json"
        "/root/.claude/settings.json"
    )

    for cfg in "${config_paths[@]}"; do
        if [ -f "$cfg" ]; then
            echo -e "  ✅ Claude configuration: $cfg"
            config_found=true
            break
        fi
    done

    if [ "$config_found" = false ]; then
        echo -e "  ${YELLOW}⚠️  Claude configuration: Not found${NC}"
        echo ""
        echo -e "  ${BLUE}Note:${NC}"
        echo "    - This is expected if you have not run Claude Code yet."
        echo "    - The script will create a configuration file during setup."
        echo "    - You can also specify a configuration path with -c."
    fi

    echo ""

    if [ "$all_ok" = false ]; then
        echo -e "${RED}❌ Prerequisite checks failed. Resolve the issues above and try again.${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ All required checks passed!${NC}"
    echo ""
}

# Find the configuration file
find_config_file() {
    # Always use the path explicitly provided with -c
    if [ -n "$CLAUDE_CONFIG" ]; then
        printf '%s\n' "$CLAUDE_CONFIG"
        return 0
    fi

    # Check common locations
    local candidates=(
        "$HOME/.claude/settings.json"
        "$HOME/.claude/settings.local.json"
        "/root/.claude/settings.json"
    )

    for cfg in "${candidates[@]}"; do
        if [ -f "$cfg" ]; then
            printf '%s\n' "$cfg"
            return 0
        fi
    done

    # Default to settings.json, even if it does not exist
    printf '%s\n' "$HOME/.claude/settings.json"
    return 0
}

# Create a base configuration when none exists
create_base_config() {
    local config_file="$1"

    # Ensure the directory exists
    local config_dir
    config_dir="$(dirname "$config_file")"
    if [ ! -d "$config_dir" ]; then
        mkdir -p -- "$config_dir"
        echo "📁 Created configuration directory: $config_dir"
    fi

    # Do not overwrite a file created after the check; new files inherit umask 077.
    (set -o noclobber; printf '{\n  "env": {}\n}\n' > "$config_file")
    echo "✅ Created base configuration file: $config_file"
    echo ""
}

# === MAIN ===

# Parse command-line arguments
CLAUDE_CONFIG=""
while getopts "c:" opt; do
    case "$opt" in
        c)
            if [ -z "$OPTARG" ]; then
                echo "The configuration file path cannot be empty" >&2
                exit 1
            fi
            CLAUDE_CONFIG="$OPTARG"
            ;;
        *) echo "Usage: $0 [-c configuration_file_path]"; exit 1 ;;
    esac
done

# 1. Checking prerequisites
check_prerequisites

# 2. Select the configuration file
CONFIG_FILE="$(find_config_file)"
case "$CONFIG_FILE" in
    /*) ;;
    *) CONFIG_FILE="$PWD/$CONFIG_FILE" ;;
esac

if { [ -e "$CONFIG_FILE" ] || [ -L "$CONFIG_FILE" ]; } && [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ The specified path is not a usable regular configuration file: $CONFIG_FILE${NC}" >&2
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}⚠️  No configuration file found. A new file will be created.${NC}"
    create_base_config "$CONFIG_FILE"
fi

echo "📁 Using configuration file: $CONFIG_FILE"
echo ""

# 3. Show the menu with two StepFun options
echo "=========================================="
echo "  Claude Code Setup - StepFun"
echo "=========================================="
echo ""
echo "Get an API key:"
echo "  StepFun: https://platform.stepfun.ai/interface-key"
echo ""
echo "Choose a StepFun connection:"
echo "  1) StepFun Official API (pay as you go)"
echo "  2) StepFun Step Plan (subscription)"
echo ""

# 4. Read the selection through /dev/tty to support piped execution
CHOICE=""
while true; do
    printf "Enter a number [1-2]: "
    if read -r CHOICE </dev/tty 2>/dev/null; then
        case "$CHOICE" in
            1|2) break ;;
            *) echo "Invalid input. Enter 1 or 2." ;;
        esac
    else
        echo ""
        echo -e "${RED}❌ Unable to read input${NC}"
        echo "Download the script and run it locally instead of using 'curl ... | bash':"
        echo "  curl -O <SCRIPT_URL>"
        echo "  bash configure_claude.sh"
        exit 1
    fi
done

echo ""

# 5. Set configuration values for the selected connection
case "$CHOICE" in
    1)
        PROVIDER="stepfun-official"
        PROMPT="Enter your StepFun API Key: "
        DEFAULT_MODEL="step-5-preview"
        BASE_URL="https://api.stepfun.ai/"
        ;;
    2)
        PROVIDER="stepfun-plan"
        PROMPT="Enter your StepFun API Key: "
        DEFAULT_MODEL="step-5-preview"
        BASE_URL="https://api.stepfun.ai/step_plan"
        ;;
esac

# 6. Read the API key
API_KEY=""
# Do not pass a newly entered key to child processes through an inherited export.
export -n API_KEY
while true; do
    printf "%s" "$PROMPT"
    if read -r -s API_KEY </dev/tty 2>/dev/null; then
        printf '\n'
        if [ -n "$API_KEY" ]; then
            break
        else
            echo "The API key cannot be empty. Please try again."
        fi
    else
        echo ""
        echo -e "${RED}❌ Unable to read input${NC}"
        echo "Download the script and run it locally."
        exit 1
    fi
done

# 7. Read the model name
printf "Model name [default: $DEFAULT_MODEL]: "
read -r MODEL_NAME </dev/tty
MODEL_NAME="${MODEL_NAME:-$DEFAULT_MODEL}"

# 8. Back up the configuration
echo ""
echo "📦 Backing up the configuration file..."
BACKUP_TMP="$(mktemp "$CONFIG_FILE.bak.$(date +%Y%m%d%H%M%S).XXXXXX")"
if ! cat -- "$CONFIG_FILE" > "$BACKUP_TMP"; then
    echo -e "${RED}❌ Backup failed. The original configuration has not been changed.${NC}" >&2
    exit 1
fi
BACKUP_FILE="$BACKUP_TMP"
BACKUP_TMP=""
echo "   Backup file: $BACKUP_FILE"
echo ""

# 9. Replace only env; preserve hooks, theme, and all other settings
echo "⚙️  Configuring Claude Code..."

# For dotfile-managed symlinks, update the target while preserving the link.
CONFIG_WRITE_FILE="$CONFIG_FILE"
while [ -L "$CONFIG_WRITE_FILE" ]; do
    CONFIG_LINK="$(readlink "$CONFIG_WRITE_FILE")"
    case "$CONFIG_LINK" in
        /*) CONFIG_WRITE_FILE="$CONFIG_LINK" ;;
        *) CONFIG_WRITE_FILE="$(dirname "$CONFIG_WRITE_FILE")/$CONFIG_LINK" ;;
    esac
done
CONFIG_TMP="$(mktemp "$CONFIG_WRITE_FILE.tmp.XXXXXX")"
if ! builtin printf '%s' "$API_KEY" | jq -e -s \
    --arg base_url "$BASE_URL" \
    --rawfile api_key /dev/stdin \
    --arg model "$MODEL_NAME" '
    if length == 1 and (.[0] | type == "object") then
        .[0] | .env = {
            "ANTHROPIC_BASE_URL": $base_url,
            "ANTHROPIC_AUTH_TOKEN": $api_key,
            "ANTHROPIC_MODEL": $model,
            "ANTHROPIC_SMALL_FAST_MODEL": $model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": $model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": $model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": $model
        }
    else
        error("The configuration file must contain exactly one JSON object")
    end
' "$CONFIG_FILE" > "$CONFIG_TMP"; then
    echo -e "${RED}❌ Unable to parse the configuration file. The original configuration has not been changed.${NC}"
    exit 1
fi
unset API_KEY
mv -- "$CONFIG_TMP" "$CONFIG_WRITE_FILE"
CONFIG_TMP=""

echo -e "  ${GREEN}✅ Claude Code configuration updated${NC}"
echo ""
echo "=========================================="
echo -e "${GREEN}✨ Setup complete!${NC}"
echo "=========================================="
echo ""
echo "📝 Configuration file: $CONFIG_FILE"
echo "📦 Backup file: $BACKUP_FILE"
echo ""
echo "⚙️  Current configuration:"
echo "   Provider: StepFun $( [ "$CHOICE" = "1" ] && echo "Official API" || echo "Step Plan" )"
echo "   API Key: Configured"
echo "   Endpoint: $BASE_URL"
echo "   Model: $MODEL_NAME"
echo ""
echo "⚠️  Important: Restart Claude Code to apply the changes."
echo ""
