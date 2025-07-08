"""
Dependency fixer factory.

This module provides a factory for creating appropriate dependency fixers
based on repository characteristics.
"""

from typing import Any, Dict, List, Optional

import structlog
from github.Repository import Repository

from ..config import Settings
from ..exceptions import DependencyFixingError
from .base import DependencyFixer
from .go_mod import GoModFixer
from .python_poetry import PythonPoetryFixer
from .typescript_npm import TypeScriptNpmFixer

logger = structlog.get_logger(__name__)


class DependencyFixerFactory:
    """
    Factory for creating appropriate dependency fixers.

    This factory analyzes repositories and returns the appropriate
    dependency fixer based on the repository's characteristics.
    """

    def __init__(self, settings: Settings):
        """
        Initialize the factory.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.fixers: List[DependencyFixer] = []
        self._initialize_fixers()

    def _initialize_fixers(self) -> None:
        """Initialize available dependency fixers."""
        # Initialize fixers based on supported languages
        if "python" in self.settings.supported_languages:
            self.fixers.append(
                PythonPoetryFixer(timeout=self.settings.dependency_update_timeout)
            )

        if "typescript" in self.settings.supported_languages:
            self.fixers.append(
                TypeScriptNpmFixer(timeout=self.settings.dependency_update_timeout)
            )

        if "javascript" in self.settings.supported_languages:
            # JavaScript uses the same fixer as TypeScript
            if not any(isinstance(f, TypeScriptNpmFixer) for f in self.fixers):
                self.fixers.append(
                    TypeScriptNpmFixer(timeout=self.settings.dependency_update_timeout)
                )

        if "go" in self.settings.supported_languages:
            self.fixers.append(
                GoModFixer(timeout=self.settings.dependency_update_timeout)
            )

        logger.info(
            "Dependency fixers initialized",
            fixers=[f.__class__.__name__ for f in self.fixers],
        )

    async def get_fixer(self, repo: Repository) -> Optional[DependencyFixer]:
        """
        Get appropriate dependency fixer for a repository.

        Args:
            repo: Repository object

        Returns:
            Appropriate dependency fixer or None
        """
        if not self.settings.enable_dependency_fixing:
            logger.info("Dependency fixing disabled", repository=repo.full_name)
            return None

        try:
            # Get repository contents to analyze
            repo_info = await self._analyze_repository(repo)

            # Find the best fixer
            for fixer in self.fixers:
                if await self._can_fixer_handle_repo(fixer, repo_info):
                    logger.info(
                        "Selected dependency fixer",
                        repository=repo.full_name,
                        fixer=fixer.__class__.__name__,
                    )
                    return fixer

            logger.info("No suitable dependency fixer found", repository=repo.full_name)
            return None

        except Exception as e:
            logger.error(
                "Failed to get dependency fixer",
                repository=repo.full_name,
                error=str(e),
            )
            raise DependencyFixingError(f"Failed to get dependency fixer: {e}")

    async def _analyze_repository(self, repo: Repository) -> Dict[str, Any]:
        """
        Analyze repository to determine characteristics.

        Args:
            repo: Repository object

        Returns:
            Repository analysis info
        """
        try:
            # Get repository contents
            contents = repo.get_contents("")

            # Ensure contents is a list
            if not isinstance(contents, list):
                contents = [contents]

            files = []
            for content in contents:
                if content.type == "file":
                    files.append(content.name)

            # Analyze file patterns
            analysis = {
                "files": files,
                "has_poetry": "pyproject.toml" in files and "poetry.lock" in files,
                "has_pip": "requirements.txt" in files or "setup.py" in files,
                "has_npm": "package.json" in files,
                "has_yarn": "yarn.lock" in files,
                "has_go": "go.mod" in files,
                "has_typescript": "tsconfig.json" in files
                or any(f.endswith(".ts") for f in files),
                "has_javascript": any(f.endswith(".js") for f in files),
                "language": None,
            }

            # Determine primary language
            if analysis["has_poetry"] or analysis["has_pip"]:
                analysis["language"] = "python"
            elif analysis["has_go"]:
                analysis["language"] = "go"
            elif analysis["has_typescript"]:
                analysis["language"] = "typescript"
            elif analysis["has_javascript"]:
                analysis["language"] = "javascript"

            logger.info(
                "Repository analysis completed",
                repository=repo.full_name,
                language=analysis["language"],
                files=len(files),
            )

            return analysis

        except Exception as e:
            logger.error(
                "Failed to analyze repository", repository=repo.full_name, error=str(e)
            )
            return {"files": [], "language": None}

    async def _can_fixer_handle_repo(
        self, fixer: DependencyFixer, repo_info: Dict[str, Any]
    ) -> bool:
        """
        Check if a fixer can handle the repository.

        Args:
            fixer: Dependency fixer
            repo_info: Repository analysis info

        Returns:
            True if fixer can handle the repository
        """
        try:
            # Check language compatibility
            if isinstance(fixer, PythonPoetryFixer):
                return bool(repo_info.get("has_poetry", False))

            elif isinstance(fixer, TypeScriptNpmFixer):
                return bool(repo_info.get("has_npm", False)) and (
                    bool(repo_info.get("has_typescript", False))
                    or bool(repo_info.get("has_javascript", False))
                )

            elif isinstance(fixer, GoModFixer):
                return bool(repo_info.get("has_go", False))

            return False

        except Exception as e:
            logger.error(
                "Failed to check fixer compatibility",
                fixer=fixer.__class__.__name__,
                error=str(e),
            )
            return False

    async def get_supported_languages(self) -> List[str]:
        """
        Get list of supported languages.

        Returns:
            List of supported languages
        """
        supported_langs = self.settings.supported_languages
        if isinstance(supported_langs, str):
            return [lang.strip() for lang in supported_langs.split(",") if lang.strip()]
        return supported_langs.copy()

    async def get_fixer_info(self) -> List[dict]:
        """
        Get information about available fixers.

        Returns:
            List of fixer information
        """
        fixer_info = []

        for fixer in self.fixers:
            try:
                info = {
                    "name": fixer.__class__.__name__,
                    "language": fixer.language,
                    "supported_files": await fixer.get_lock_files(),
                    "tools_available": await fixer.validate_tools(),
                }
                fixer_info.append(info)
            except Exception as e:
                logger.error(
                    "Failed to get fixer info",
                    fixer=fixer.__class__.__name__,
                    error=str(e),
                )

        return fixer_info

    async def validate_all_fixers(self) -> dict:
        """
        Validate all available fixers.

        Returns:
            Validation results for all fixers
        """
        validation_results = {}

        for fixer in self.fixers:
            try:
                is_valid = await fixer.validate_tools()
                validation_results[fixer.__class__.__name__] = {
                    "valid": is_valid,
                    "language": fixer.language,
                    "error": None,
                }
            except Exception as e:
                validation_results[fixer.__class__.__name__] = {
                    "valid": False,
                    "language": fixer.language,
                    "error": str(e),
                }

        return validation_results
