# Gemini Assistant Guidelines for RenovateAgent

This document provides guidelines for the Gemini AI assistant when working on the `RenovateAgent` project. Please adhere to these rules to ensure consistency, quality, and alignment with project standards.

## 1. Documentation-First Approach

Your primary directive is to **understand before acting**. Always begin by consulting the project's documentation.

### 1.1. Pre-Change Analysis
Before writing or modifying any code, you MUST:
1.  **Locate Developer Documentation**: Find and prioritize reading documents like `developer.md`, `CONTRIBUTING.md`, `README.md`, and architectural documents.
2.  **Analyze Contents**: Extract key information regarding:
    -   Environment setup and required variables.
    -   Project architecture and design patterns.
    -   Testing strategies and command.
    -   Configuration requirements.
    -   Tooling and API usage patterns.
3.  **Validate Against Code**: Treat documentation with healthy skepticism. Verify that documented procedures, function signatures, and configuration options match the current state of the codebase. Note any discrepancies.

### 1.2. Documentation Maintenance
As you work, you are responsible for maintaining the quality of the documentation.
-   **Update as you go**: If your changes affect behavior, configuration, or APIs, update the corresponding documentation in the same commit/PR.
-   **Report Outdated Docs**: If you find outdated or incorrect documentation that is outside the scope of your current task, report it clearly, noting the discrepancy and its potential impact.
-   **Documentation Triggers**: Update documentation when making changes to: APIs, system processes, configuration, architecture, or user-facing features.

## 2. Git Commit Standards

All Git commit messages MUST adhere to the **Conventional Commits specification**. This is crucial for automated changelog generation and semantic versioning.

### 2.1. Format
```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### 2.2. Types
You MUST use one of the following types:
-   `feat`: A new feature for the user.
-   `fix`: A bug fix for the user.
-   `docs`: Documentation only changes.
-   `style`: Code style changes (formatting, etc.).
-   `refactor`: A code change that neither fixes a bug nor adds a feature.
-   `perf`: A code change that improves performance.
-   `test`: Adding or correcting tests.
-   `build`: Changes to the build system or external dependencies.
-   `ci`: Changes to CI configuration and scripts.
-   `chore`: Other changes that don't modify source or test files.
-   `revert`: Reverts a previous commit.

### 2.3. Breaking Changes
Indicate breaking changes by:
-   Appending `!` to the type/scope (e.g., `feat(api)!: remove deprecated endpoint`).
-   Adding a `BREAKING CHANGE:` section in the commit footer.

### 2.4. Description
The description MUST:
-   Be in the imperative mood (e.g., "add feature" not "added feature").
-   Start with a lowercase letter.
-   Not end with a period.

## 3. Code Quality Automation

This project uses `pre-commit` to enforce code quality and standards automatically.

### 3.1. Setup
-   Check for a `.pre-commit-config.yaml` file in the repository root.
-   If it exists, ensure `pre-commit` is installed (`pip install pre-commit`).
-   Install the git hooks with `pre-commit install`.

### 3.2. Usage
-   Hooks run automatically on `git commit` against staged files.
-   A failing hook will prevent the commit. You must fix the issues and re-add the files.
-   You can run hooks manually on all files with `pre-commit run --all-files`.

## 4. Date Handling

For any tasks requiring the current date, you MUST use the `YYYY-MM-DD` format.
-   **Command to get date**: `date +%Y-%m-%d`
-   **Usage**: Execute this command and use the output for consistency. Do not hardcode dates.
