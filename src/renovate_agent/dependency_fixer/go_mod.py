"""
Go module dependency fixer.

This module provides dependency fixing capabilities for Go projects
using Go modules.
"""

import re
from pathlib import Path
from typing import Any, Dict, List

import structlog

from .base import DependencyFixer

logger = structlog.get_logger(__name__)


class GoModFixer(DependencyFixer):
    """
    Dependency fixer for Go projects using Go modules.

    This fixer handles updating go.sum files when dependencies
    change in go.mod.
    """

    def __init__(self, timeout: int = 600):
        """
        Initialize the Go module fixer.

        Args:
            timeout: Maximum time for operations (seconds)
        """
        super().__init__(timeout)
        self.language = "go"
        self.supported_files = ["go.mod", "go.sum"]

    async def can_fix(self, repo_path: Path) -> bool:
        """
        Check if this fixer can handle the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            True if Go module project is detected
        """
        go_mod_path = repo_path / "go.mod"

        # Check if go.mod exists
        if not await self.check_file_exists(go_mod_path):
            logger.debug("go.mod not found", repo_path=str(repo_path))
            return False

        # Verify it's a valid Go module file
        try:
            with open(go_mod_path) as f:
                content = f.read()
                if not content.strip().startswith("module "):
                    logger.debug("Invalid go.mod format", repo_path=str(repo_path))
                    return False
        except Exception as e:
            logger.error("Failed to read go.mod",
                        repo_path=str(repo_path),
                        error=str(e))
            return False

        go_sum_path = repo_path / "go.sum"
        logger.info("Go module project detected",
                   repo_path=str(repo_path),
                   has_go_sum=await self.check_file_exists(go_sum_path))

        return True

    async def fix_dependencies(self, repo_path: Path, branch: str) -> Dict[str, Any]:
        """
        Fix dependencies using Go modules.

        Args:
            repo_path: Path to the repository
            branch: Branch name

        Returns:
            Fix result
        """
        logger.info("Starting Go module dependency fix",
                   repo_path=str(repo_path),
                   branch=branch)

        try:
            # Check if Go is available
            if not await self.validate_tools():
                return {
                    "success": False,
                    "error": "Go is not available"
                }

            # Run go mod tidy to clean up dependencies
            tidy_result = await self._run_go_mod_tidy(repo_path)
            if not tidy_result["success"]:
                return tidy_result

            # Run go mod download to ensure all dependencies are available
            download_result = await self._run_go_mod_download(repo_path)
            if not download_result["success"]:
                # Don't fail if download fails, tidy might be enough
                logger.warning("go mod download failed, but continuing",
                              repo_path=str(repo_path),
                              error=download_result.get("error"))

            # Check for changes
            changed_files = await self.get_changed_files(repo_path)

            logger.info("Go module dependency fix completed",
                       repo_path=str(repo_path),
                       changed_files=changed_files)

            return {
                "success": True,
                "changes": changed_files,
                "commands_run": ["go mod tidy", "go mod download"],
                "message": "Go module dependencies updated successfully"
            }

        except Exception as e:
            logger.error("Go module dependency fix failed",
                        repo_path=str(repo_path),
                        error=str(e))
            return {
                "success": False,
                "error": f"Go module dependency fix failed: {e}"
            }

    async def _run_go_mod_tidy(self, repo_path: Path) -> Dict[str, Any]:
        """
        Run go mod tidy command.

        Args:
            repo_path: Path to the repository

        Returns:
            Command result
        """
        logger.info("Running go mod tidy", repo_path=str(repo_path))

        cmd = ["go", "mod", "tidy"]
        result = await self.run_command(cmd, repo_path)

        if result["success"]:
            logger.info("go mod tidy completed successfully",
                       repo_path=str(repo_path))
            return {"success": True, "output": result["stdout"]}
        else:
            logger.error("go mod tidy failed",
                        repo_path=str(repo_path),
                        error=result["stderr"])
            return {
                "success": False,
                "error": f"go mod tidy failed: {result['stderr']}"
            }

    async def _run_go_mod_download(self, repo_path: Path) -> Dict[str, Any]:
        """
        Run go mod download command.

        Args:
            repo_path: Path to the repository

        Returns:
            Command result
        """
        logger.info("Running go mod download", repo_path=str(repo_path))

        cmd = ["go", "mod", "download"]
        result = await self.run_command(cmd, repo_path)

        if result["success"]:
            logger.info("go mod download completed successfully",
                       repo_path=str(repo_path))
            return {"success": True, "output": result["stdout"]}
        else:
            logger.warning("go mod download failed",
                          repo_path=str(repo_path),
                          error=result["stderr"])
            return {
                "success": False,
                "error": f"go mod download failed: {result['stderr']}"
            }

    async def get_lock_files(self) -> List[str]:
        """
        Get list of lock files this fixer handles.

        Returns:
            List of lock file names
        """
        return ["go.sum"]

    async def validate_tools(self) -> bool:
        """
        Validate that Go is available.

        Returns:
            True if Go is available
        """
        try:
            # Check if go command is available
            result = await self.run_command(["go", "version"], Path("."))

            if result["success"]:
                version_info = result["stdout"].strip()
                logger.info("Go validation successful", version=version_info)
                return True
            else:
                logger.error("Go validation failed", error=result["stderr"])
                return False

        except Exception as e:
            logger.error("Go validation failed", error=str(e))
            return False

    async def get_dependency_info(self, repo_path: Path) -> Dict[str, Any]:
        """
        Get information about Go module dependencies.

        Args:
            repo_path: Path to the repository

        Returns:
            Dependency information
        """
        try:
            # Get module list
            cmd = ["go", "list", "-m", "all"]
            result = await self.run_command(cmd, repo_path)

            dependencies = []
            if result["success"]:
                for line in result["stdout"].split('\n'):
                    line = line.strip()
                    if line and ' ' in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            dependencies.append({
                                "name": parts[0],
                                "version": parts[1],
                                "indirect": "(indirect)" in line
                            })

            # Get outdated dependencies
            outdated_info = await self._get_outdated_modules(repo_path)

            # Parse go.mod for additional info
            go_mod_info = await self._parse_go_mod(repo_path)

            return {
                "total_dependencies": len(dependencies),
                "dependencies": dependencies,
                "outdated": outdated_info,
                "module_info": go_mod_info
            }

        except Exception as e:
            logger.error("Failed to get dependency info",
                        repo_path=str(repo_path),
                        error=str(e))
            return {"error": str(e)}

    async def _get_outdated_modules(self, repo_path: Path) -> Dict[str, Any]:
        """
        Get information about outdated modules.

        Args:
            repo_path: Path to the repository

        Returns:
            Outdated module information
        """
        try:
            # Get available updates
            cmd = ["go", "list", "-u", "-m", "all"]
            result = await self.run_command(cmd, repo_path)

            outdated = []
            if result["success"]:
                for line in result["stdout"].split('\n'):
                    line = line.strip()
                    if line and '[' in line and ']' in line:
                        # Parse format: module version [available_version]
                        match = re.match(r'(.+?)\s+(.+?)\s+\[(.+?)\]', line)
                        if match:
                            module, current, available = match.groups()
                            outdated.append({
                                "name": module,
                                "current": current,
                                "available": available
                            })

            return {
                "count": len(outdated),
                "modules": outdated
            }

        except Exception as e:
            logger.error("Failed to get outdated modules",
                        repo_path=str(repo_path),
                        error=str(e))
            return {"error": str(e)}

    async def _parse_go_mod(self, repo_path: Path) -> Dict[str, Any]:
        """
        Parse go.mod file for module information.

        Args:
            repo_path: Path to the repository

        Returns:
            Module information
        """
        try:
            go_mod_path = repo_path / "go.mod"
            with open(go_mod_path) as f:
                content = f.read()

            # Extract module name
            module_match = re.search(r'^module\s+(.+)$', content, re.MULTILINE)
            module_name = module_match.group(1) if module_match else None

            # Extract Go version
            go_version_match = re.search(r'^go\s+(\d+\.\d+)$', content, re.MULTILINE)
            go_version = go_version_match.group(1) if go_version_match else None

            # Count require statements
            require_count = len(re.findall(r'^\s*[a-zA-Z0-9\.\-\/]+\s+v', content, re.MULTILINE))

            return {
                "module_name": module_name,
                "go_version": go_version,
                "require_count": require_count
            }

        except Exception as e:
            logger.error("Failed to parse go.mod",
                        repo_path=str(repo_path),
                        error=str(e))
            return {"error": str(e)}

    async def check_lock_file_consistency(self, repo_path: Path) -> Dict[str, Any]:
        """
        Check if go.sum is consistent with go.mod.

        Args:
            repo_path: Path to the repository

        Returns:
            Consistency check result
        """
        try:
            # Run go mod verify to check consistency
            cmd = ["go", "mod", "verify"]
            result = await self.run_command(cmd, repo_path)

            if result["success"]:
                return {
                    "consistent": True,
                    "message": "go.sum is consistent with go.mod"
                }
            else:
                return {
                    "consistent": False,
                    "error": result["stderr"],
                    "message": "go.sum inconsistency detected"
                }

        except Exception as e:
            logger.error("Failed to check module consistency",
                        repo_path=str(repo_path),
                        error=str(e))
            return {
                "consistent": False,
                "error": str(e)
            }

    async def clean_module_cache(self, repo_path: Path) -> Dict[str, Any]:
        """
        Clean Go module cache.

        Args:
            repo_path: Path to the repository

        Returns:
            Clean result
        """
        try:
            cmd = ["go", "clean", "-modcache"]
            result = await self.run_command(cmd, repo_path)

            if result["success"]:
                logger.info("Go module cache cleaned successfully",
                           repo_path=str(repo_path))
                return {"success": True, "message": "Module cache cleaned"}
            else:
                return {
                    "success": False,
                    "error": result["stderr"]
                }

        except Exception as e:
            logger.error("Failed to clean module cache",
                        repo_path=str(repo_path),
                        error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
