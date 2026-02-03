#!/bin/bash
#
# apply-best-practices.sh
# Copies project scaffold best practices to an existing project
#
# Usage: ./apply-best-practices.sh /path/to/target/project

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}!${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_info() { echo -e "  $1"; }

# Check arguments
if [ -z "$1" ]; then
    echo "Usage: $0 <target-project-path>"
    echo ""
    echo "Options:"
    echo "  --dry-run    Show what would be copied without making changes"
    echo ""
    echo "Example:"
    echo "  $0 /path/to/my-existing-project"
    echo "  $0 --dry-run /path/to/my-existing-project"
    exit 1
fi

DRY_RUN=false
TARGET_DIR=""

# Parse arguments
for arg in "$@"; do
    if [ "$arg" == "--dry-run" ]; then
        DRY_RUN=true
    else
        TARGET_DIR="$arg"
    fi
done

# Validate target directory
if [ ! -d "$TARGET_DIR" ]; then
    print_error "Target directory does not exist: $TARGET_DIR"
    exit 1
fi

# Convert to absolute path
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"

echo ""
echo "=========================================="
echo " Apply Best Practices to Existing Project"
echo "=========================================="
echo ""
echo "Source template: $TEMPLATE_DIR"
echo "Target project:  $TARGET_DIR"
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Mode: DRY RUN (no changes will be made)${NC}"
fi
echo ""

# Helper function to copy file
copy_file() {
    local src="$1"
    local dest="$2"
    local desc="$3"

    if [ ! -f "$src" ]; then
        print_warning "Source not found: $src"
        return
    fi

    if [ -f "$dest" ]; then
        print_warning "$desc already exists (skipped): $dest"
        return
    fi

    if [ "$DRY_RUN" = true ]; then
        print_info "[DRY RUN] Would copy: $desc"
    else
        cp "$src" "$dest"
        print_success "Copied: $desc"
    fi
}

# Helper function to create directory
ensure_dir() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        if [ "$DRY_RUN" = true ]; then
            print_info "[DRY RUN] Would create directory: $dir"
        else
            mkdir -p "$dir"
            print_success "Created directory: $dir"
        fi
    fi
}

echo "--- Configuration Files ---"

# .editorconfig
copy_file "$TEMPLATE_DIR/.editorconfig" "$TARGET_DIR/.editorconfig" ".editorconfig"

# .gitignore - special handling (append mode)
if [ -f "$TARGET_DIR/.gitignore" ]; then
    if [ "$DRY_RUN" = true ]; then
        print_info "[DRY RUN] Would create: .gitignore.template (for manual merge)"
    else
        cp "$TEMPLATE_DIR/.gitignore" "$TARGET_DIR/.gitignore.template"
        print_success "Created: .gitignore.template (merge manually with existing .gitignore)"
    fi
else
    copy_file "$TEMPLATE_DIR/.gitignore" "$TARGET_DIR/.gitignore" ".gitignore"
fi

echo ""
echo "--- GitHub Templates ---"

# Create .github directories
ensure_dir "$TARGET_DIR/.github"
ensure_dir "$TARGET_DIR/.github/ISSUE_TEMPLATE"
ensure_dir "$TARGET_DIR/.github/workflows"

# Issue templates
copy_file "$TEMPLATE_DIR/.github/ISSUE_TEMPLATE/bug_report.md" \
          "$TARGET_DIR/.github/ISSUE_TEMPLATE/bug_report.md" \
          "Issue template: bug_report.md"

copy_file "$TEMPLATE_DIR/.github/ISSUE_TEMPLATE/feature_request.md" \
          "$TARGET_DIR/.github/ISSUE_TEMPLATE/feature_request.md" \
          "Issue template: feature_request.md"

copy_file "$TEMPLATE_DIR/.github/ISSUE_TEMPLATE/config.yml" \
          "$TARGET_DIR/.github/ISSUE_TEMPLATE/config.yml" \
          "Issue template: config.yml"

# PR template
copy_file "$TEMPLATE_DIR/.github/PULL_REQUEST_TEMPLATE.md" \
          "$TARGET_DIR/.github/PULL_REQUEST_TEMPLATE.md" \
          "Pull request template"

# CODEOWNERS
copy_file "$TEMPLATE_DIR/.github/CODEOWNERS" \
          "$TARGET_DIR/.github/CODEOWNERS" \
          "CODEOWNERS (remember to update with your team)"

# CI workflow
copy_file "$TEMPLATE_DIR/.github/workflows/ci.yml" \
          "$TARGET_DIR/.github/workflows/ci.yml" \
          "CI workflow (customize for your build/test commands)"

echo ""
echo "--- Documentation Files ---"

copy_file "$TEMPLATE_DIR/CONTRIBUTING.md" \
          "$TARGET_DIR/CONTRIBUTING.md" \
          "CONTRIBUTING.md"

copy_file "$TEMPLATE_DIR/CHANGELOG.md" \
          "$TARGET_DIR/CHANGELOG.md" \
          "CHANGELOG.md"

# Only copy LICENSE if none exists
if [ ! -f "$TARGET_DIR/LICENSE" ] && [ ! -f "$TARGET_DIR/LICENSE.md" ] && [ ! -f "$TARGET_DIR/LICENSE.txt" ]; then
    copy_file "$TEMPLATE_DIR/LICENSE" "$TARGET_DIR/LICENSE" "LICENSE (MIT)"
else
    print_warning "LICENSE already exists (skipped)"
fi

echo ""
echo "=========================================="
echo " Summary"
echo "=========================================="
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "This was a dry run. No changes were made."
    echo "Run without --dry-run to apply changes."
else
    echo "Files have been copied to your project."
    echo ""
    echo "Next steps:"
    echo "  1. Update .github/CODEOWNERS with your team's GitHub usernames"
    echo "  2. Customize .github/workflows/ci.yml for your build/test commands"
    echo "  3. Edit CONTRIBUTING.md with your project's setup instructions"
    echo "  4. If .gitignore.template was created, merge it with your .gitignore"
    echo "  5. Update CHANGELOG.md to start from your current version"
    echo ""
    echo "Commit convention to adopt:"
    echo "  Add:      New features"
    echo "  Fix:      Bug fixes"
    echo "  Update:   Changes to existing features"
    echo "  Remove:   Deleted functionality"
    echo "  Docs:     Documentation changes"
    echo "  Test:     Test additions/changes"
    echo "  Refactor: Code restructuring"
fi

echo ""
