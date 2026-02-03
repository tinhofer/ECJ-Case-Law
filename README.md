# Claude-Code

A project scaffolded with best practices for modern development.

## Getting Started

### Prerequisites

- Git
- Your preferred programming language runtime

### Installation

```bash
git clone <repository-url>
cd Claude-Code
```

## Project Structure

```
Claude-Code/
├── .github/              # GitHub templates and workflows
│   ├── ISSUE_TEMPLATE/   # Issue templates
│   ├── workflows/        # CI/CD workflows
│   └── PULL_REQUEST_TEMPLATE.md
├── scripts/              # Utility scripts
│   └── apply-best-practices.sh  # Apply scaffold to existing projects
├── src/                  # Source code (create as needed)
├── tests/                # Test files (create as needed)
├── docs/                 # Documentation (create as needed)
├── .editorconfig         # Editor configuration
├── .gitignore            # Git ignore rules
├── CHANGELOG.md          # Version history
├── CONTRIBUTING.md       # Contribution guidelines
├── LICENSE               # MIT License
└── README.md             # This file
```

## Usage

### For New Projects

Fork or clone this repository and customize it for your needs:

```bash
git clone https://github.com/tinhofer/Claude-Code.git my-new-project
cd my-new-project
rm -rf .git && git init
git add . && git commit -m "Add: initial project scaffold"
```

### For Existing Projects

Use the included script to apply best practices to an existing project:

```bash
# Preview what will be copied (dry run)
./scripts/apply-best-practices.sh --dry-run /path/to/your-project

# Apply the best practices
./scripts/apply-best-practices.sh /path/to/your-project
```

The script copies:
- `.editorconfig` - Code style configuration
- `.gitignore` - Comprehensive ignore patterns (as template if one exists)
- `.github/ISSUE_TEMPLATE/` - Bug report and feature request templates
- `.github/PULL_REQUEST_TEMPLATE.md` - PR checklist
- `.github/CODEOWNERS` - Code ownership configuration
- `.github/workflows/ci.yml` - CI/CD pipeline skeleton
- `CONTRIBUTING.md` - Contribution guidelines
- `CHANGELOG.md` - Version history template

After running the script, customize the files for your project's specific needs.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a list of changes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Thanks to all contributors
