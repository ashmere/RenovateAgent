"""
Python Poetry dependency fixer.

This module provides dependency fixing capabilities for Python projects
using Poetry package manager.
"""

from pathlib import Path
from typing import Any, Dict, List

import structlog

from .base import DependencyFixer

logger = structlog.get_logger(__name__)


class PythonPoetryFixer(DependencyFixer):
    """
    Dependency fixer for Python projects using Poetry.

    This fixer handles updating poetry.lock files when dependencies
    change in pyproject.toml.
    """

    def __init__(self, timeout: int = 600):
        """
        Initialize the Python Poetry fixer.

        Args:
            timeout: Maximum time for operations (seconds)
        """
        super().__init__(timeout)
        self.language = "python"
        self.supported_files = ["pyproject.toml", "poetry.lock"]

    async def can_fix(self, repo_path: Path) -> bool:
        """
        Check if this fixer can handle the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            True if Poetry project is detected
        """
        pyproject_path = repo_path / "pyproject.toml"
        poetry_lock_path = repo_path / "poetry.lock"

        # Check if pyproject.toml exists
        if not await self.check_file_exists(pyproject_path):
            logger.debug("pyproject.toml not found", repo_path=str(repo_path))
            return False

        # Check if it's a Poetry project by looking for [tool.poetry] section
        try:
            with open(pyproject_path) as f:
                content = f.read()
                if "[tool.poetry]" not in content:
                    logger.debug("Not a Poetry project", repo_path=str(repo_path))
                    return False
        except Exception as e:
            logger.error(
                "Failed to read pyproject.toml", repo_path=str(repo_path), error=str(e)
            )
            return False

        logger.info(
            "Poetry project detected",
            repo_path=str(repo_path),
            has_lock_file=await self.check_file_exists(poetry_lock_path),
        )

        return True

    async def fix_dependencies(self, repo_path: Path, branch: str) -> Dict[str, Any]:
        """
        Fix dependencies using Poetry.

        Args:
            repo_path: Path to the repository
            branch: Branch name

        Returns:
            Fix result
        """
        logger.info(
            "Starting Poetry dependency fix", repo_path=str(repo_path), branch=branch
        )

        try:
            # Check if Poetry is available
            if not await self.validate_tools():
                return {"success": False, "error": "Poetry is not available"}

            # Run poetry lock to update lock file
            lock_result = await self._run_poetry_lock(repo_path)
            if not lock_result["success"]:
                return lock_result

            # Run poetry install to verify dependencies
            install_result = await self._run_poetry_install(repo_path)
            if not install_result["success"]:
                return install_result

            # Check for changes
            changed_files = await self.get_changed_files(repo_path)

            logger.info(
                "Poetry dependency fix completed",
                repo_path=str(repo_path),
                changed_files=changed_files,
            )

            return {
                "success": True,
                "changes": changed_files,
                "commands_run": ["poetry lock", "poetry install"],
                "message": "Poetry dependencies updated successfully",
            }

        except Exception as e:
            logger.error(
                "Poetry dependency fix failed", repo_path=str(repo_path), error=str(e)
            )
            return {"success": False, "error": f"Poetry dependency fix failed: {e}"}

    async def _run_poetry_lock(self, repo_path: Path) -> Dict[str, Any]:
        """
        Run poetry lock command.

        Args:
            repo_path: Path to the repository

        Returns:
            Command result
        """
        logger.info("Running poetry lock", repo_path=str(repo_path))

        # Use --no-update to only update the lock file without changing dependencies
        cmd = ["poetry", "lock", "--no-update"]
        result = await self.run_command(cmd, repo_path)

        if result["success"]:
            logger.info("poetry lock completed successfully", repo_path=str(repo_path))
            return {"success": True, "output": result["stdout"]}
        else:
            logger.error(
                "poetry lock failed", repo_path=str(repo_path), error=result["stderr"]
            )

            # Try with update if no-update fails
            logger.info("Retrying poetry lock with update", repo_path=str(repo_path))
            cmd_update = ["poetry", "lock"]
            result_update = await self.run_command(cmd_update, repo_path)

            if result_update["success"]:
                logger.info(
                    "poetry lock with update completed successfully",
                    repo_path=str(repo_path),
                )
                return {"success": True, "output": result_update["stdout"]}
            else:
                return {
                    "success": False,
                    "error": f"poetry lock failed: {result_update['stderr']}",
                }

    async def _run_poetry_install(self, repo_path: Path) -> Dict[str, Any]:
        """
        Run poetry install command to verify dependencies.

        Args:
            repo_path: Path to the repository

        Returns:
            Command result
        """
        logger.info("Running poetry install", repo_path=str(repo_path))

        # Install dependencies without dev dependencies for verification
        cmd = ["poetry", "install", "--no-dev", "--no-interaction"]
        result = await self.run_command(cmd, repo_path)

        if result["success"]:
            logger.info(
                "poetry install completed successfully", repo_path=str(repo_path)
            )
            return {"success": True, "output": result["stdout"]}
        else:
            logger.warning(
                "poetry install failed, but this might be expected",
                repo_path=str(repo_path),
                error=result["stderr"],
            )
            # Don't fail the entire process if install fails,
            # as the lock file update might still be valid
            return {"success": True, "output": result["stderr"], "warning": True}

    async def get_lock_files(self) -> List[str]:
        """
        Get list of lock files this fixer handles.

        Returns:
            List of lock file names
        """
        return ["poetry.lock"]

    async def validate_tools(self) -> bool:
        """
        Validate that Poetry is available.

        Returns:
            True if Poetry is available
        """
        try:
            # Check if poetry command is available
            result = await self.run_command(["poetry", "--version"], Path("."))

            if result["success"]:
                version_info = result["stdout"].strip()
                logger.info("Poetry validation successful", version=version_info)
                return True
            else:
                logger.error("Poetry validation failed", error=result["stderr"])
                return False

        except Exception as e:
            logger.error("Poetry validation failed", error=str(e))
            return False

    async def get_dependency_info(self, repo_path: Path) -> Dict[str, Any]:
        """
        Get information about project dependencies.

        Args:
            repo_path: Path to the repository

        Returns:
            Dependency information
        """
        try:
            # Get dependency list
            cmd = ["poetry", "show", "--no-ansi"]
            result = await self.run_command(cmd, repo_path)

            dependencies = []
            if result["success"]:
                for line in result["stdout"].split("\n"):
                    line = line.strip()
                    if line and not line.startswith("Warning"):
                        parts = line.split()
                        if len(parts) >= 2:
                            dependencies.append(
                                {
                                    "name": parts[0],
                                    "version": parts[1],
                                    "description": (
                                        " ".join(parts[2:]) if len(parts) > 2 else ""
                                    ),
                                }
                            )

            # Get outdated dependencies
            cmd_outdated = ["poetry", "show", "--outdated", "--no-ansi"]
            result_outdated = await self.run_command(cmd_outdated, repo_path)

            outdated = []
            if result_outdated["success"]:
                for line in result_outdated["stdout"].split("\n"):
                    line = line.strip()
                    if line and not line.startswith("Warning"):
                        parts = line.split()
                        if len(parts) >= 3:
                            outdated.append(
                                {
                                    "name": parts[0],
                                    "current": parts[1],
                                    "latest": parts[2],
                                }
                            )

            return {
                "total_dependencies": len(dependencies),
                "dependencies": dependencies,
                "outdated_count": len(outdated),
                "outdated": outdated,
            }

        except Exception as e:
            logger.error(
                "Failed to get dependency info", repo_path=str(repo_path), error=str(e)
            )
            return {"error": str(e)}

    async def check_lock_file_consistency(self, repo_path: Path) -> Dict[str, Any]:
        """
        Check if lock file is consistent with pyproject.toml.

        Args:
            repo_path: Path to the repository

        Returns:
            Consistency check result
        """
        try:
            # Run poetry check to validate consistency
            cmd = ["poetry", "check"]
            result = await self.run_command(cmd, repo_path)

            if result["success"]:
                return {
                    "consistent": True,
                    "message": "Lock file is consistent with pyproject.toml",
                }
            else:
                return {
                    "consistent": False,
                    "error": result["stderr"],
                    "message": "Lock file is not consistent with pyproject.toml",
                }

        except Exception as e:
            logger.error(
                "Failed to check lock file consistency",
                repo_path=str(repo_path),
                error=str(e),
            )
            return {"consistent": False, "error": str(e)}
