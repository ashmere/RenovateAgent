"""
TypeScript/JavaScript npm dependency fixer.

This module provides dependency fixing capabilities for TypeScript/JavaScript
projects using npm or yarn package managers.
"""

import json
from pathlib import Path
from typing import Any

import structlog

from .base import DependencyFixer

logger = structlog.get_logger(__name__)


class TypeScriptNpmFixer(DependencyFixer):
    """
    Dependency fixer for TypeScript/JavaScript projects using npm or yarn.

    This fixer handles updating package-lock.json or yarn.lock files when
    dependencies change in package.json.
    """

    def __init__(self, timeout: int = 600):
        """
        Initialize the TypeScript/JavaScript npm fixer.

        Args:
            timeout: Maximum time for operations (seconds)
        """
        super().__init__(timeout)
        self.language = "typescript"
        self.supported_files = ["package.json", "package-lock.json", "yarn.lock"]
        self.package_manager: str | None = None  # Will be detected: 'npm' or 'yarn'

    async def can_fix(self, repo_path: Path) -> bool:
        """
        Check if this fixer can handle the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            True if npm/yarn project is detected
        """
        package_json_path = repo_path / "package.json"

        # Check if package.json exists
        if not await self.check_file_exists(package_json_path):
            logger.debug("package.json not found", repo_path=str(repo_path))
            return False

        # Detect package manager
        yarn_lock_path = repo_path / "yarn.lock"
        npm_lock_path = repo_path / "package-lock.json"

        if await self.check_file_exists(yarn_lock_path):
            self.package_manager = "yarn"
        elif await self.check_file_exists(npm_lock_path):
            self.package_manager = "npm"
        else:
            # Default to npm if no lock file exists
            self.package_manager = "npm"

        logger.info(
            "JavaScript/TypeScript project detected",
            repo_path=str(repo_path),
            package_manager=self.package_manager,
            has_yarn_lock=await self.check_file_exists(yarn_lock_path),
            has_npm_lock=await self.check_file_exists(npm_lock_path),
        )

        return True

    async def fix_dependencies(self, repo_path: Path, branch: str) -> dict[str, Any]:
        """
        Fix dependencies using npm or yarn.

        Args:
            repo_path: Path to the repository
            branch: Branch name

        Returns:
            Fix result
        """
        logger.info(
            "Starting JavaScript/TypeScript dependency fix",
            repo_path=str(repo_path),
            branch=branch,
            package_manager=self.package_manager,
        )

        try:
            # Check if package manager is available
            if not await self.validate_tools():
                return {
                    "success": False,
                    "error": f"{self.package_manager} is not available",
                }

            # Run dependency installation
            if self.package_manager == "yarn":
                install_result = await self._run_yarn_install(repo_path)
            else:
                install_result = await self._run_npm_install(repo_path)

            if not install_result["success"]:
                return install_result

            # Check for changes
            changed_files = await self.get_changed_files(repo_path)

            logger.info(
                "JavaScript/TypeScript dependency fix completed",
                repo_path=str(repo_path),
                package_manager=self.package_manager,
                changed_files=changed_files,
            )

            return {
                "success": True,
                "changes": changed_files,
                "package_manager": self.package_manager,
                "commands_run": self._get_commands_run(),
                "message": f"Dependencies updated successfully using {self.package_manager}",
            }

        except Exception as e:
            logger.error(
                "JavaScript/TypeScript dependency fix failed",
                repo_path=str(repo_path),
                error=str(e),
            )
            return {"success": False, "error": f"Dependency fix failed: {e}"}

    async def _run_npm_install(self, repo_path: Path) -> dict[str, Any]:
        """
        Run npm install commands.

        Args:
            repo_path: Path to the repository

        Returns:
            Command result
        """
        logger.info("Running npm install", repo_path=str(repo_path))

        # Clean npm cache first to avoid potential issues
        clean_result = await self.run_command(
            ["npm", "cache", "clean", "--force"], repo_path
        )
        if not clean_result["success"]:
            logger.warning(
                "npm cache clean failed",
                repo_path=str(repo_path),
                error=clean_result["stderr"],
            )

        # Run npm install
        cmd = ["npm", "install", "--no-audit", "--no-fund", "--prefer-offline"]
        result = await self.run_command(cmd, repo_path)

        if result["success"]:
            logger.info("npm install completed successfully", repo_path=str(repo_path))
            return {"success": True, "output": result["stdout"]}
        else:
            logger.error(
                "npm install failed", repo_path=str(repo_path), error=result["stderr"]
            )

            # Try npm ci if regular install fails
            logger.info("Retrying with npm ci", repo_path=str(repo_path))
            ci_cmd = ["npm", "ci", "--no-audit", "--no-fund"]
            ci_result = await self.run_command(ci_cmd, repo_path)

            if ci_result["success"]:
                logger.info("npm ci completed successfully", repo_path=str(repo_path))
                return {"success": True, "output": ci_result["stdout"]}
            else:
                return {
                    "success": False,
                    "error": f"npm install/ci failed: {ci_result['stderr']}",
                }

    async def _run_yarn_install(self, repo_path: Path) -> dict[str, Any]:
        """
        Run yarn install commands.

        Args:
            repo_path: Path to the repository

        Returns:
            Command result
        """
        logger.info("Running yarn install", repo_path=str(repo_path))

        # Run yarn install
        cmd = ["yarn", "install", "--frozen-lockfile", "--non-interactive"]
        result = await self.run_command(cmd, repo_path)

        if result["success"]:
            logger.info("yarn install completed successfully", repo_path=str(repo_path))
            return {"success": True, "output": result["stdout"]}
        else:
            logger.error(
                "yarn install with frozen lockfile failed",
                repo_path=str(repo_path),
                error=result["stderr"],
            )

            # Try without frozen lockfile if it fails
            logger.info(
                "Retrying yarn install without frozen lockfile",
                repo_path=str(repo_path),
            )
            cmd_update = ["yarn", "install", "--non-interactive"]
            result_update = await self.run_command(cmd_update, repo_path)

            if result_update["success"]:
                logger.info(
                    "yarn install completed successfully", repo_path=str(repo_path)
                )
                return {"success": True, "output": result_update["stdout"]}
            else:
                return {
                    "success": False,
                    "error": f"yarn install failed: {result_update['stderr']}",
                }

    def _get_commands_run(self) -> list[str]:
        """Get list of commands that were run."""
        if self.package_manager == "yarn":
            return ["yarn install --frozen-lockfile", "yarn install"]
        else:
            return ["npm cache clean --force", "npm install", "npm ci"]

    async def get_lock_files(self) -> list[str]:
        """
        Get list of lock files this fixer handles.

        Returns:
            List of lock file names
        """
        return ["package-lock.json", "yarn.lock"]

    async def validate_tools(self) -> bool:
        """
        Validate that required package manager is available.

        Returns:
            True if package manager is available
        """
        try:
            # Check if package manager is available
            if self.package_manager == "yarn":
                result = await self.run_command(["yarn", "--version"], Path("."))
            else:
                result = await self.run_command(["npm", "--version"], Path("."))

            if result["success"]:
                version_info = result["stdout"].strip()
                logger.info(
                    "Package manager validation successful",
                    package_manager=self.package_manager,
                    version=version_info,
                )
                return True
            else:
                logger.error(
                    "Package manager validation failed",
                    package_manager=self.package_manager,
                    error=result["stderr"],
                )
                return False

        except Exception as e:
            logger.error(
                "Package manager validation failed",
                package_manager=self.package_manager,
                error=str(e),
            )
            return False

    async def get_dependency_info(self, repo_path: Path) -> dict[str, Any]:
        """
        Get information about project dependencies.

        Args:
            repo_path: Path to the repository

        Returns:
            Dependency information
        """
        try:
            # Read package.json
            package_json_path = repo_path / "package.json"
            with open(package_json_path) as f:
                package_data = json.load(f)

            dependencies = package_data.get("dependencies", {})
            dev_dependencies = package_data.get("devDependencies", {})
            peer_dependencies = package_data.get("peerDependencies", {})

            # Get outdated packages
            outdated_info = await self._get_outdated_packages(repo_path)

            return {
                "package_manager": self.package_manager,
                "total_dependencies": len(dependencies),
                "total_dev_dependencies": len(dev_dependencies),
                "total_peer_dependencies": len(peer_dependencies),
                "dependencies": dependencies,
                "dev_dependencies": dev_dependencies,
                "peer_dependencies": peer_dependencies,
                "outdated": outdated_info,
            }

        except Exception as e:
            logger.error(
                "Failed to get dependency info", repo_path=str(repo_path), error=str(e)
            )
            return {"error": str(e)}

    async def _get_outdated_packages(self, repo_path: Path) -> dict[str, Any]:
        """
        Get information about outdated packages.

        Args:
            repo_path: Path to the repository

        Returns:
            Outdated package information
        """
        try:
            if self.package_manager == "yarn":
                cmd = ["yarn", "outdated", "--json"]
            else:
                cmd = ["npm", "outdated", "--json"]

            result = await self.run_command(cmd, repo_path)

            if result["success"] and result["stdout"]:
                if self.package_manager == "yarn":
                    # Yarn outdated returns multiple JSON objects
                    outdated = {}
                    for line in result["stdout"].split("\n"):
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if data.get("type") == "table":
                                    outdated = data.get("data", {})
                                    break
                            except json.JSONDecodeError:
                                continue
                else:
                    # npm outdated returns a single JSON object
                    outdated = json.loads(result["stdout"])

                return {"count": len(outdated), "packages": outdated}
            else:
                return {"count": 0, "packages": {}}

        except Exception as e:
            logger.error(
                "Failed to get outdated packages",
                repo_path=str(repo_path),
                error=str(e),
            )
            return {"error": str(e)}

    async def check_lock_file_consistency(self, repo_path: Path) -> dict[str, Any]:
        """
        Check if lock file is consistent with package.json.

        Args:
            repo_path: Path to the repository

        Returns:
            Consistency check result
        """
        try:
            if self.package_manager == "yarn":
                # Yarn check
                cmd = ["yarn", "check", "--verify-tree"]
            else:
                # npm audit (basic consistency check)
                cmd = ["npm", "audit", "--audit-level", "none"]

            result = await self.run_command(cmd, repo_path)

            if result["success"]:
                return {
                    "consistent": True,
                    "message": f"Lock file is consistent with package.json ({self.package_manager})",
                }
            else:
                return {
                    "consistent": False,
                    "error": result["stderr"],
                    "message": f"Lock file inconsistency detected ({self.package_manager})",
                }

        except Exception as e:
            logger.error(
                "Failed to check lock file consistency",
                repo_path=str(repo_path),
                error=str(e),
            )
            return {"consistent": False, "error": str(e)}
