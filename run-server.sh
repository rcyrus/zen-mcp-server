#!/bin/bash
set -euo pipefail

# ============================================================================
# Zen MCP Server Setup Script
# 
# Uses uv for Python management exclusively.
# Handles environment setup, dependency installation, and configuration.
# ============================================================================

# ----------------------------------------------------------------------------
# Constants and Configuration
# ----------------------------------------------------------------------------

# Colors for output (ANSI codes work on all platforms)
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m' # No Color

# Configuration
readonly VENV_PATH=".venv"
readonly DOCKER_CLEANED_FLAG=".docker_cleaned"
readonly DESKTOP_CONFIG_FLAG=".desktop_configured"
readonly LOG_DIR="logs"
readonly LOG_FILE="mcp_server.log"

# ----------------------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------------------

# Print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1" >&2
}

print_error() {
    echo -e "${RED}✗${NC} $1" >&2
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1" >&2
}

print_info() {
    echo -e "${YELLOW}$1${NC}" >&2
}

# Get the script's directory (works on all platforms)
get_script_dir() {
    cd "$(dirname "$0")" && pwd
}

# Extract version from config.py
get_version() {
    grep -E '^__version__ = ' config.py 2>/dev/null | sed 's/__version__ = "\(.*\)"/\1/' || echo "unknown"
}

# Clear Python cache files to prevent import issues
clear_python_cache() {
    print_info "Clearing Python cache files..."
    find . -name "*.pyc" -delete 2>/dev/null || true
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    print_success "Python cache cleared"
}

# ----------------------------------------------------------------------------
# Platform Detection Functions
# ----------------------------------------------------------------------------

# Get cross-platform Python executable path from venv
get_venv_python_path() {
    local venv_path="$1"
    
    # Convert to absolute path for consistent behavior across shell environments
    local abs_venv_path
    abs_venv_path=$(cd "$(dirname "$venv_path")" && pwd)/$(basename "$venv_path")

    # Check for both Unix and Windows Python executable paths
    if [[ -f "$abs_venv_path/bin/python" ]]; then
        echo "$abs_venv_path/bin/python"
    elif [[ -f "$abs_venv_path/Scripts/python.exe" ]]; then
        echo "$abs_venv_path/Scripts/python.exe"
    else
        return 1  # No Python executable found
    fi
}

# Detect the operating system
detect_os() {
    case "$OSTYPE" in
        darwin*)  echo "macos" ;;
        linux*)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        msys*|cygwin*|win32) echo "windows" ;;
        *)        echo "unknown" ;;
    esac
}

# Get Claude config path based on platform
get_claude_config_path() {
    local os_type=$(detect_os)

    case "$os_type" in
        macos)
            echo "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
            ;;
        linux)
            echo "$HOME/.config/Claude/claude_desktop_config.json"
            ;;
        wsl)
            local win_appdata
            if command -v wslvar &> /dev/null; then
                win_appdata=$(wslvar APPDATA 2>/dev/null)
            fi

            if [[ -n "${win_appdata:-}" ]]; then
                echo "$(wslpath "$win_appdata")/Claude/claude_desktop_config.json"
            else
                print_warning "Could not determine Windows user path automatically. Please ensure APPDATA is set correctly or provide the full path manually."
                echo "/mnt/c/Users/$USER/AppData/Roaming/Claude/claude_desktop_config.json"
            fi
            ;;
        windows)
            echo "$APPDATA/Claude/claude_desktop_config.json"
            ;;
        *)
            echo ""
            ;;
    esac
}

# ----------------------------------------------------------------------------
# Docker Cleanup Functions
# ----------------------------------------------------------------------------

# Clean up old Docker artifacts
cleanup_docker() {
    # Skip if already cleaned or Docker not available
    [[ -f "$DOCKER_CLEANED_FLAG" ]] && return 0

    if ! command -v docker &> /dev/null || ! docker info &> /dev/null 2>&1; then
        return 0
    fi

    local found_artifacts=false

    # Define containers to remove
    local containers=(
        "gemini-mcp-server"
        "gemini-mcp-redis"
        "zen-mcp-server"
        "zen-mcp-redis"
        "zen-mcp-log-monitor"
    )

    # Remove containers
    for container in "${containers[@]}"; do
        if docker ps -a --format "{{.Names}}" | grep -q "^${container}$" 2>/dev/null; then
            if [[ "$found_artifacts" == false ]]; then
                echo "One-time Docker cleanup..."
                found_artifacts=true
            fi
            echo "  Removing container: $container"
            docker stop "$container" >/dev/null 2>&1 || true
            docker rm "$container" >/dev/null 2>&1 || true
        fi
    done

    # Remove images
    local images=("gemini-mcp-server:latest" "zen-mcp-server:latest")
    for image in "${images[@]}"; do
        if docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^${image}$" 2>/dev/null; then
            if [[ "$found_artifacts" == false ]]; then
                echo "One-time Docker cleanup..."
                found_artifacts=true
            fi
            echo "  Removing image: $image"
            docker rmi "$image" >/dev/null 2>&1 || true
        fi
    done

    # Remove volumes
    local volumes=("redis_data" "mcp_logs")
    for volume in "${volumes[@]}"; do
        if docker volume ls --format "{{.Name}}" | grep -q "^${volume}$" 2>/dev/null; then
            if [[ "$found_artifacts" == false ]]; then
                echo "One-time Docker cleanup..."
                found_artifacts=true
            fi
            echo "  Removing volume: $volume"
            docker volume rm "$volume" >/dev/null 2>&1 || true
        fi
    done

    if [[ "$found_artifacts" == true ]]; then
        print_success "Docker cleanup complete"
    fi

    touch "$DOCKER_CLEANED_FLAG"
}

# ----------------------------------------------------------------------------
# Python Environment Functions
# ----------------------------------------------------------------------------

# Check if uv is installed
check_uv_installed() {
    if ! command -v uv &> /dev/null; then
        print_error "uv is not installed. Please install uv first:"
        echo ""
        local os_type=$(detect_os)
        case "$os_type" in
            macos)
                echo "  brew install uv"
                echo "  # or"
                echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
                ;;
            linux|wsl)
                echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
                echo "  # or"
                echo "  pip install uv"
                ;;
            windows)
                echo "  powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
                echo "  # or"
                echo "  pip install uv"
                ;;
        esac
        echo ""
        echo "After installing uv, run this script again."
        return 1
    fi
    return 0
}



# Setup environment using uv
setup_environment() {
    # Check if uv is installed
    check_uv_installed || return 1
    
    local venv_python=""
    
    # Check if .venv exists and was created by uv
    if [[ -d "$VENV_PATH" ]]; then
        # Try to get Python from existing venv
        if venv_python=$(get_venv_python_path "$VENV_PATH"); then
            # Verify it's a working Python
            if $venv_python --version &>/dev/null 2>&1; then
                local python_version=$($venv_python --version 2>&1)
                print_success "Using existing environment with $python_version"
                
                # Convert to absolute path
                local abs_venv_python
                if cd "$(dirname "$venv_python")" 2>/dev/null; then
                    abs_venv_python=$(pwd)/$(basename "$venv_python")
                    venv_python="$abs_venv_python"
                    cd - >/dev/null
                fi
                
                echo "$venv_python"
                return 0
            fi
        fi
        
        # Existing venv is broken, remove it
        print_warning "Existing environment appears broken, recreating..."
        rm -rf "$VENV_PATH"
    fi
    
    # Create new environment with uv
    print_info "Creating environment with uv..."
    
    # Try Python 3.12 first (preferred)
    local uv_output
    if uv_output=$(uv venv --python 3.12 "$VENV_PATH" 2>&1); then
        if venv_python=$(get_venv_python_path "$VENV_PATH"); then
            print_success "Created environment with Python 3.12"
        fi
    # Fall back to any available Python
    elif uv_output=$(uv venv "$VENV_PATH" 2>&1); then
        if venv_python=$(get_venv_python_path "$VENV_PATH"); then
            local python_version=$($venv_python --version 2>&1)
            print_success "Created environment with $python_version"
        fi
    else
        print_error "Failed to create environment with uv"
        echo "Error: $uv_output"
        return 1
    fi
    
    # Verify Python was found
    if [[ -z "$venv_python" ]]; then
        print_error "Python executable not found in virtual environment"
        return 1
    fi
    
    # Convert to absolute path for MCP registration
    local abs_venv_python
    if cd "$(dirname "$venv_python")" 2>/dev/null; then
        abs_venv_python=$(pwd)/$(basename "$venv_python")
        venv_python="$abs_venv_python"
        cd - >/dev/null
    fi
    
    echo "$venv_python"
    return 0
}


# Check if package is installed
check_package() {
    local python_cmd="$1"
    local module_name="$2"
    "$python_cmd" -c "import importlib, sys; importlib.import_module(sys.argv[1])" "$module_name" &>/dev/null
}

# Install dependencies
install_dependencies() {
    local python_cmd="$1"

    # Check if pyproject.toml exists
    if [[ ! -f "pyproject.toml" ]]; then
        print_error "pyproject.toml not found!"
        return 1
    fi
    
    echo ""
    print_info "Setting up Zen MCP Server..."
    echo "Installing required components:"
    echo "  • MCP protocol library"
    echo "  • AI model connectors"
    echo "  • Data validation tools"
    echo "  • Environment configuration"
    echo ""
    


    # Use uv sync to install dependencies from pyproject.toml
    echo -n "Installing packages..."
    local install_output
    
    # Run uv sync
    if install_output=$(uv sync 2>&1); then
        echo -e "\r${GREEN}✓ Setup complete!${NC}                    "
        return 0
    else
        echo -e "\r${RED}✗ Setup failed${NC}                      "
        echo ""
        echo "Installation error:"
        echo "$install_output" | head -20
        echo ""
        echo "Try running manually:"
        echo "  uv sync"
        echo ""
        echo "Or add packages individually:"
        echo "  uv add mcp google-generativeai openai pydantic python-dotenv"
        return 1
    fi
}

# ----------------------------------------------------------------------------
# Environment Configuration Functions
# ----------------------------------------------------------------------------

# Setup .env file
setup_env_file() {
    if [[ -f .env ]]; then
        print_success ".env file already exists"
        migrate_env_file
        return 0
    fi

    if [[ ! -f .env.example ]]; then
        print_error ".env.example not found!"
        return 1
    fi

    cp .env.example .env
    print_success "Created .env from .env.example"

    # Detect sed version for cross-platform compatibility
    local sed_cmd
    if sed --version >/dev/null 2>&1; then
        sed_cmd="sed -i"  # GNU sed (Linux)
    else
        sed_cmd="sed -i ''"  # BSD sed (macOS)
    fi

    # Update API keys from environment if present
    local api_keys=(
        "GEMINI_API_KEY:your_gemini_api_key_here"
        "OPENAI_API_KEY:your_openai_api_key_here"
        "XAI_API_KEY:your_xai_api_key_here"
        "MOONSHOT_API_KEY:your_moonshot_api_key_here"
        "GROQ_API_KEY:your_groq_api_key_here"
        "DIAL_API_KEY:your_dial_api_key_here"
        "VERTEX_PROJECT_ID:your_vertex_project_id_here"
        "VERTEX_REGION:us-central1"
        "OPENROUTER_API_KEY:your_openrouter_api_key_here"
    )

    for key_pair in "${api_keys[@]}"; do
        local key_name="${key_pair%%:*}"
        local placeholder="${key_pair##*:}"
        local key_value="${!key_name:-}"

        if [[ -n "$key_value" ]]; then
            $sed_cmd "s/$placeholder/$key_value/" .env
            print_success "Updated .env with $key_name from environment"
        fi
    done

    return 0
}

# Migrate .env file from Docker to standalone format
migrate_env_file() {
    # Check if migration is needed
    if ! grep -q "host\.docker\.internal" .env 2>/dev/null; then
        return 0
    fi

    print_warning "Migrating .env from Docker to standalone format..."

    # Create backup
    cp .env .env.backup_$(date +%Y%m%d_%H%M%S)

    # Detect sed version for cross-platform compatibility
    local sed_cmd
    if sed --version >/dev/null 2>&1; then
        sed_cmd="sed -i"  # GNU sed (Linux)
    else
        sed_cmd="sed -i ''"  # BSD sed (macOS)
    fi

    # Replace host.docker.internal with localhost
    $sed_cmd 's/host\.docker\.internal/localhost/g' .env

    print_success "Migrated Docker URLs to localhost in .env"
    echo "  (Backup saved as .env.backup_*)"
}

# Check API keys and warn if missing (non-blocking)
check_api_keys() {
    local has_key=false
    local api_keys=(
        "GEMINI_API_KEY:your_gemini_api_key_here"
        "OPENAI_API_KEY:your_openai_api_key_here"
        "XAI_API_KEY:your_xai_api_key_here"
        "MOONSHOT_API_KEY:your_moonshot_api_key_here"
        "GROQ_API_KEY:your_groq_api_key_here"
        "DIAL_API_KEY:your_dial_api_key_here"
        "OPENROUTER_API_KEY:your_openrouter_api_key_here"
    )

    for key_pair in "${api_keys[@]}"; do
        local key_name="${key_pair%%:*}"
        local placeholder="${key_pair##*:}"
        local key_value="${!key_name:-}"

        if [[ -n "$key_value" ]] && [[ "$key_value" != "$placeholder" ]]; then
            print_success "$key_name configured"
            has_key=true
        fi
    done
    
    # Check Vertex AI configuration (both project ID and region must be set together)
    local vertex_project_id="${VERTEX_PROJECT_ID:-}"
    local vertex_region="${VERTEX_REGION:-us-central1}"
    local vertex_project_placeholder="your_vertex_project_id_here"
    
    if [[ -n "$vertex_project_id" ]] && [[ "$vertex_project_id" != "$vertex_project_placeholder" ]]; then
        print_success "Vertex AI configured (project: $vertex_project_id, region: $vertex_region)"
        has_key=true
    elif [[ -n "$vertex_region" ]] && [[ "$vertex_region" != "us-central1" ]]; then
        print_warning "VERTEX_REGION set but VERTEX_PROJECT_ID not configured"
        echo "  For Vertex AI, both VERTEX_PROJECT_ID and VERTEX_REGION must be set" >&2
    fi
    
    # Check custom API URL
    if [[ -n "${CUSTOM_API_URL:-}" ]]; then
        print_success "CUSTOM_API_URL configured: $CUSTOM_API_URL"
        has_key=true
    fi

    if [[ "$has_key" == false ]]; then
        echo "  MOONSHOT_API_KEY=your-actual-key" >&2
        echo "  GROQ_API_KEY=your-actual-key" >&2
    fi

    return 0  # Always return success to continue setup
}


# ----------------------------------------------------------------------------
# Claude Integration Functions
# ----------------------------------------------------------------------------

# Check if MCP is added to Claude CLI and verify it's correct
check_claude_cli_integration() {
    local python_cmd="$1"
    local server_path="$2"

    if ! command -v claude &> /dev/null; then
        echo ""
        print_warning "Claude CLI not found"
        echo ""
        read -p "Would you like to add Zen to Claude Code? (Y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            print_info "Skipping Claude Code integration"
            return 0
        fi

        echo ""
        echo "Please install Claude Code first:"
        echo "  Visit: https://docs.anthropic.com/en/docs/claude-code/cli-usage"
        echo ""
        echo "Then run this script again to register MCP."
        return 1
    fi

    # Check if zen is registered
    local mcp_list=$(claude mcp list 2>/dev/null)
    if echo "$mcp_list" | grep -q "zen"; then
        # Check if it's using the old Docker command
        if echo "$mcp_list" | grep -E "zen.*docker|zen.*compose" &>/dev/null; then
            print_warning "Found old Docker-based Zen registration, updating..."
            claude mcp remove zen -s user 2>/dev/null || true

            # Re-add with correct Python command
            if claude mcp add zen -s user -- "$python_cmd" "$server_path" 2>/dev/null; then
                print_success "Updated Zen to become a standalone script"
                return 0
            else
                echo ""
                echo "Failed to update MCP registration. Please run manually:"
                echo "  claude mcp remove zen -s user"
                echo "  claude mcp add zen -s user -- $python_cmd $server_path"
                return 1
            fi
        else
            # Verify the registered path matches current setup
            local expected_cmd="$python_cmd $server_path"
            if echo "$mcp_list" | grep -F "$server_path" &>/dev/null; then
                return 0
            else
                print_warning "Zen registered with different path, updating..."
                claude mcp remove zen -s user 2>/dev/null || true

                if claude mcp add zen -s user -- "$python_cmd" "$server_path" 2>/dev/null; then
                    print_success "Updated Zen with current path"
                    return 0
                else
                    echo ""
                    echo "Failed to update MCP registration. Please run manually:"
                    echo "  claude mcp remove zen -s user"
                    echo "  claude mcp add zen -s user -- $python_cmd $server_path"
                    return 1
                fi
            fi
        fi
    else
        # Not registered at all, ask user if they want to add it
        echo ""
        read -p "Add Zen to Claude Code? (Y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            print_info "To add manually later, run:"
            echo "  claude mcp add zen -s user -- $python_cmd $server_path"
            return 0
        fi

        print_info "Registering Zen with Claude Code..."
        if claude mcp add zen -s user -- "$python_cmd" "$server_path" 2>/dev/null; then
            print_success "Successfully added Zen to Claude Code"
            return 0
        else
            echo ""
            echo "Failed to add automatically. To add manually, run:"
            echo "  claude mcp add zen -s user -- $python_cmd $server_path"
            return 1
        fi
    fi
}

# Check and update Claude Desktop configuration
check_claude_desktop_integration() {
    local python_cmd="$1"
    local server_path="$2"

    # Skip if already configured (check flag)
    if [[ -f "$DESKTOP_CONFIG_FLAG" ]]; then
        return 0
    fi

    local config_path=$(get_claude_config_path)
    if [[ -z "$config_path" ]]; then
        print_warning "Unable to determine Claude Desktop config path for this platform"
        return 0
    fi

    echo ""
    read -p "Configure Zen for Claude Desktop? (Y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        print_info "Skipping Claude Desktop integration"
        touch "$DESKTOP_CONFIG_FLAG"  # Don't ask again
        return 0
    fi

    # Create config directory if it doesn't exist
    local config_dir=$(dirname "$config_path")
    mkdir -p "$config_dir" 2>/dev/null || true

    # Handle existing config
    if [[ -f "$config_path" ]]; then
        print_info "Updating existing Claude Desktop config..."

        # Check for old Docker config and remove it
        if grep -q "docker.*compose.*zen\|zen.*docker" "$config_path" 2>/dev/null; then
            print_warning "Removing old Docker-based MCP configuration..."
            # Create backup
            cp "$config_path" "${config_path}.backup_$(date +%Y%m%d_%H%M%S)"

            # Remove old zen config using a more robust approach
            local temp_file=$(mktemp)
            python3 -c "
import json
import sys

try:
    with open('$config_path', 'r') as f:
        config = json.load(f)

    # Remove zen from mcpServers if it exists
    if 'mcpServers' in config and 'zen' in config['mcpServers']:
        del config['mcpServers']['zen']
        print('Removed old zen MCP configuration')

    with open('$temp_file', 'w') as f:
        json.dump(config, f, indent=2)

except Exception as e:
    print(f'Error processing config: {e}', file=sys.stderr)
    sys.exit(1)
" && mv "$temp_file" "$config_path"
        fi

        # Add new config
        local temp_file=$(mktemp)
        python3 -c "
import json
import sys

try:
    with open('$config_path', 'r') as f:
        config = json.load(f)
except:
    config = {}

# Ensure mcpServers exists
if 'mcpServers' not in config:
    config['mcpServers'] = {}

# Add zen server
config['mcpServers']['zen'] = {
    'command': '$python_cmd',
    'args': ['$server_path']
}

with open('$temp_file', 'w') as f:
    json.dump(config, f, indent=2)
" && mv "$temp_file" "$config_path"

    else
        print_info "Creating new Claude Desktop config..."
        cat > "$config_path" << EOF
{
  "mcpServers": {
    "zen": {
      "command": "$python_cmd",
      "args": ["$server_path"]
    }
  }
}
EOF
    fi

    if [[ $? -eq 0 ]]; then
        print_success "Successfully configured Claude Desktop"
        echo "  Config: $config_path"
        echo "  Restart Claude Desktop to use the new MCP server"
        touch "$DESKTOP_CONFIG_FLAG"
    else
        print_error "Failed to update Claude Desktop config"
        echo "Manual config location: $config_path"
        echo "Add this configuration:"
        cat << EOF
{
  "mcpServers": {
    "zen": {
      "command": "$python_cmd",
      "args": ["$server_path"]
    }
  }
}
EOF
    fi
}

# Check and update Gemini CLI configuration
check_gemini_cli_integration() {
    local script_dir="$1"
    local zen_wrapper="$script_dir/zen-mcp-server"

    # Check if Gemini settings file exists
    local gemini_config="$HOME/.gemini/settings.json"
    if [[ ! -f "$gemini_config" ]]; then
        # Gemini CLI not installed or not configured
        return 0
    fi

    # Check if zen is already configured
    if grep -q '"zen"' "$gemini_config" 2>/dev/null; then
        # Already configured
        return 0
    fi

    # Ask user if they want to add Zen to Gemini CLI
    echo ""
    read -p "Configure Zen for Gemini CLI? (Y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        print_info "Skipping Gemini CLI integration"
        return 0
    fi

    # Ensure wrapper script exists
    if [[ ! -f "$zen_wrapper" ]]; then
        print_info "Creating wrapper script for Gemini CLI..."
        cat > "$zen_wrapper" << 'EOF'
#!/bin/bash
# Wrapper script for Gemini CLI compatibility
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
exec .zen_venv/bin/python server.py "$@"
EOF
        chmod +x "$zen_wrapper"
        print_success "Created zen-mcp-server wrapper script"
    fi

    # Update Gemini settings
    print_info "Updating Gemini CLI configuration..."

    # Create backup
    cp "$gemini_config" "${gemini_config}.backup_$(date +%Y%m%d_%H%M%S)"

    # Add zen configuration using Python for proper JSON handling
    local temp_file=$(mktemp)
    python3 -c "
import json
import sys

try:
    with open('$gemini_config', 'r') as f:
        config = json.load(f)

    # Ensure mcpServers exists
    if 'mcpServers' not in config:
        config['mcpServers'] = {}

    # Add zen server
    config['mcpServers']['zen'] = {
        'command': '$zen_wrapper'
    }

    with open('$temp_file', 'w') as f:
        json.dump(config, f, indent=2)

except Exception as e:
    print(f'Error processing config: {e}', file=sys.stderr)
    sys.exit(1)
" && mv "$temp_file" "$gemini_config"

    if [[ $? -eq 0 ]]; then
        print_success "Successfully configured Gemini CLI"
        echo "  Config: $gemini_config"
        echo "  Restart Gemini CLI to use Zen MCP Server"
    else
        print_error "Failed to update Gemini CLI config"
        echo "Manual config location: $gemini_config"
        echo "Add this configuration:"
        cat << EOF
{
  "mcpServers": {
    "zen": {
      "command": "$zen_wrapper"
    }
  }
}
EOF
    fi
}

# Display configuration instructions
display_config_instructions() {
    local python_cmd="$1"
    local server_path="$2"

    # Get script directory for Gemini CLI config
    local script_dir=$(dirname "$server_path")

    echo ""
    local config_header="ZEN MCP SERVER CONFIGURATION"
    echo "===== $config_header ====="
    printf '%*s\n' "$((${#config_header} + 12))" | tr ' ' '='
    echo ""
    echo "To use Zen MCP Server with your Claude clients:"
    echo ""

    print_info "1. For Claude Code (CLI):"
    echo -e "   ${GREEN}claude mcp add zen -s user -- $python_cmd $server_path${NC}"
    echo ""

    print_info "2. For Claude Desktop:"
    echo "   Add this configuration to your Claude Desktop config file:"
    echo ""
    cat << EOF
   {
     "mcpServers": {
       "zen": {
         "command": "$python_cmd",
         "args": ["$server_path"]
       }
     }
   }
EOF

    # Show platform-specific config location
    local config_path=$(get_claude_config_path)
    if [[ -n "$config_path" ]]; then
        echo ""
        print_info "   Config file location:"
        echo -e "   ${YELLOW}$config_path${NC}"
    fi

    echo ""
    print_info "3. Restart Claude Desktop after updating the config file"
    echo ""

    print_info "For Gemini CLI:"
    echo "   Add this configuration to ~/.gemini/settings.json:"
    echo ""
    cat << EOF
   {
     "mcpServers": {
       "zen": {
         "command": "$script_dir/zen-mcp-server"
       }
     }
   }
EOF
    echo ""
}

# Display setup instructions
display_setup_instructions() {
    local python_cmd="$1"
    local server_path="$2"

    echo ""
    local setup_header="SETUP COMPLETE"
    echo "===== $setup_header ====="
    printf '%*s\n' "$((${#setup_header} + 12))" | tr ' ' '='
    echo ""
    print_success "Zen is ready to use!"
    
    # Display enabled/disabled tools if DISABLED_TOOLS is configured
    if [[ -n "${DISABLED_TOOLS:-}" ]]; then
        echo ""
        print_info "Tool Configuration:"
        
        # Dynamically discover all available tools from the tools directory
        # Excludes: __pycache__, shared modules, models.py, listmodels.py, version.py
        local all_tools=()
        for tool_file in tools/*.py; do
            if [[ -f "$tool_file" ]]; then
                local tool_name=$(basename "$tool_file" .py)
                # Skip non-tool files
                if [[ "$tool_name" != "models" && "$tool_name" != "listmodels" && "$tool_name" != "version" && "$tool_name" != "__init__" ]]; then
                    all_tools+=("$tool_name")
                fi
            fi
        done
        
        # Convert DISABLED_TOOLS to array
        IFS=',' read -ra disabled_array <<< "$DISABLED_TOOLS"
        
        # Trim whitespace from disabled tools
        local disabled_tools=()
        for tool in "${disabled_array[@]}"; do
            disabled_tools+=("$(echo "$tool" | xargs)")
        done
        
        # Determine enabled tools
        local enabled_tools=()
        for tool in "${all_tools[@]}"; do
            local is_disabled=false
            for disabled in "${disabled_tools[@]}"; do
                if [[ "$tool" == "$disabled" ]]; then
                    is_disabled=true
                    break
                fi
            done
            if [[ "$is_disabled" == false ]]; then
                enabled_tools+=("$tool")
            fi
        done
        
        # Display enabled tools
        echo ""
        echo -e "  ${GREEN}Enabled Tools (${#enabled_tools[@]}):${NC}"
        local enabled_list=""
        for tool in "${enabled_tools[@]}"; do
            if [[ -n "$enabled_list" ]]; then
                enabled_list+=", "
            fi
            enabled_list+="$tool"
        done
        echo "    $enabled_list"
        
        # Display disabled tools
        echo ""
        echo -e "  ${YELLOW}Disabled Tools (${#disabled_tools[@]}):${NC}"
        local disabled_list=""
        for tool in "${disabled_tools[@]}"; do
            if [[ -n "$disabled_list" ]]; then
                disabled_list+=", "
            fi
            disabled_list+="$tool"
        done
        echo "    $disabled_list"
        
        echo ""
        echo "  To enable more tools, edit the DISABLED_TOOLS variable in .env"
    fi
}

# ----------------------------------------------------------------------------
# Log Management Functions
# ----------------------------------------------------------------------------

# Show help message
show_help() {
    local version=$(get_version)
    local header="🤖 Zen MCP Server v$version"
    echo "$header"
    printf '%*s\n' "${#header}" | tr ' ' '='
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help      Show this help message"
    echo "  -v, --version   Show version information"
    echo "  -f, --follow    Follow server logs in real-time"
    echo "  -c, --config    Show configuration instructions for Claude clients"
    echo "  --clear-cache   Clear Python cache and exit (helpful for import issues)"
    echo ""
    echo "Examples:"
    echo "  $0              Setup and start the MCP server"
    echo "  $0 -f           Setup and follow logs"
    echo "  $0 -c           Show configuration instructions"
    echo "  $0 --version    Show version only"
    echo "  $0 --clear-cache Clear Python cache (fixes import issues)"
    echo ""
    echo "For more information, visit:"
    echo "  https://github.com/BeehiveInnovations/zen-mcp-server"
}

# Show version only
show_version() {
    local version=$(get_version)
    echo "$version"
}

# Follow logs
follow_logs() {
    local log_path="$LOG_DIR/$LOG_FILE"

    echo "Following server logs (Ctrl+C to stop)..."
    echo ""

    # Create logs directory and file if they don't exist
    mkdir -p "$LOG_DIR"
    touch "$log_path"

    # Follow the log file
    tail -f "$log_path"
}

# ----------------------------------------------------------------------------
# Main Function
# ----------------------------------------------------------------------------

main() {
    # Parse command line arguments
    local arg="${1:-}"

    case "$arg" in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--version)
            show_version
            exit 0
            ;;
        -c|--config)
            # Setup minimal environment to get paths for config display
            echo "Setting up environment for configuration display..."
            echo ""
            local python_cmd
            python_cmd=$(setup_environment) || exit 1
            local script_dir=$(get_script_dir)
            local server_path="$script_dir/server.py"
            display_config_instructions "$python_cmd" "$server_path"
            exit 0
            ;;
        -f|--follow)
            # Continue with normal setup then follow logs
            ;;
        --clear-cache)
            # Clear cache and exit
            clear_python_cache
            print_success "Cache cleared successfully"
            echo ""
            echo "You can now run './run-server.sh' normally"
            exit 0
            ;;
        "")
            # Normal setup without following logs
            ;;
        *)
            print_error "Unknown option: $arg"
            echo "" >&2
            show_help
            exit 1
            ;;
    esac

    # Display header
    local main_header="🤖 Zen MCP Server"
    echo "$main_header"
    printf '%*s\n' "${#main_header}" | tr ' ' '='

    # Get and display version
    local version=$(get_version)
    echo "Version: $version"
    echo ""

    # Check if venv exists
    if [[ ! -d "$VENV_PATH" ]]; then
        echo "Setting up Python environment for first time..."
    fi

    # Step 1: Docker cleanup
    cleanup_docker

    # Step 1.5: Clear Python cache to prevent import issues
    clear_python_cache

    # Step 2: Setup environment file
    setup_env_file || exit 1

    # Step 3: Source .env file
    if [[ -f .env ]]; then
        set -a
        source .env
        set +a
    fi

    # Step 4: Check API keys (non-blocking - just warn if missing)
    check_api_keys

    # Step 5: Setup Python environment (uv-first approach)
    local python_cmd
    python_cmd=$(setup_environment) || exit 1

    # Step 6: Install dependencies
    install_dependencies "$python_cmd" || exit 1

    # Step 7: Get absolute server path
    local script_dir=$(get_script_dir)
    local server_path="$script_dir/server.py"

    # Step 8: Display setup instructions
    display_setup_instructions "$python_cmd" "$server_path"

    # Step 9: Check Claude integrations
    check_claude_cli_integration "$python_cmd" "$server_path"
    check_claude_desktop_integration "$python_cmd" "$server_path"

    # Step 10: Check Gemini CLI integration
    check_gemini_cli_integration "$script_dir"

    # Step 11: Display log information
    echo ""
    echo "Logs will be written to: $script_dir/$LOG_DIR/$LOG_FILE"
    echo ""

    # Step 12: Handle command line arguments
    if [[ "$arg" == "-f" ]] || [[ "$arg" == "--follow" ]]; then
        follow_logs
    else
        echo "To follow logs: ./run-server.sh -f"
        echo "To show config: ./run-server.sh -c"
        echo "To update: git pull, then run ./run-server.sh again"
        echo ""
        echo "Happy coding! 🎉"
    fi
}

# ----------------------------------------------------------------------------
# Script Entry Point
# ----------------------------------------------------------------------------

# Run main function with all arguments
main "$@"
