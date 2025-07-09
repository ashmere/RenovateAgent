"""
Base dependency fixer abstract class.

This module defines the interface that all dependency fixers must implement.
"""

import asyncio
import shutil
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class DependencyFixer(ABC):
    """
    Abstract base class for dependency fixers.

    All language-specific dependency fixers must inherit from this class
    and implement the required methods.
    """

    def __init__(self, timeout: int = 600):
        """
        Initialize the dependency fixer.

        Args:
            timeout: Maximum time to spend on dependency fixing (seconds)
        """
        self.timeout = timeout
        self.supported_files: list[str] = []
        self.language: str = ""

    @abstractmethod
    async def can_fix(self, repo_path: Path) -> bool:
        """
        Check if this fixer can handle the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            True if this fixer can handle the repository
        """
        pass

    @abstractmethod
    async def fix_dependencies(self, repo_path: Path, branch: str) -> dict[str, Any]:
        """
        Fix dependencies in the repository.

        Args:
            repo_path: Path to the repository
            branch: Branch name to work on

        Returns:
            Dictionary with fix results
        """
        pass

    @abstractmethod
    async def get_lock_files(self) -> list[str]:
        """
        Get list of lock files this fixer handles.

        Returns:
            List of lock file names
        """
        pass

    @abstractmethod
    async def validate_tools(self) -> bool:
        """
        Validate that required tools are available.

        Returns:
            True if all required tools are available
        """
        pass

    async def clone_repository(
        self, repo_url: str, repo_path: Path, branch: str
    ) -> bool:
        """
        Clone a repository.

        Args:
            repo_url: Repository URL
            repo_path: Path to clone to
            branch: Branch to clone

        Returns:
            True if successful
        """
        try:
            cmd = [
                "git",
                "clone",
                "--single-branch",
                "--branch",
                branch,
                repo_url,
                str(repo_path),
            ]

            logger.info(
                "Cloning repository",
                repo_url=repo_url,
                branch=branch,
                path=str(repo_path),
            )

            result = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                result.communicate(), timeout=self.timeout
            )

            if result.returncode != 0:
                logger.error(
                    "Failed to clone repository",
                    repo_url=repo_url,
                    branch=branch,
                    error=stderr.decode("utf-8"),
                )
                return False

            logger.info(
                "Repository cloned successfully", repo_url=repo_url, branch=branch
            )
            return True

        except asyncio.TimeoutError:
            logger.error("Repository clone timeout", repo_url=repo_url, branch=branch)
            return False
        except Exception as e:
            logger.error(
                "Failed to clone repository",
                repo_url=repo_url,
                branch=branch,
                error=str(e),
            )
            return False

    async def run_command(self, cmd: list[str], cwd: Path) -> dict[str, Any]:
        """
        Run a command in the repository.

        Args:
            cmd: Command to run
            cwd: Working directory

        Returns:
            Command result
        """
        try:
            logger.info("Running command", command=" ".join(cmd), cwd=str(cwd))

            result = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                result.communicate(), timeout=self.timeout
            )

            return {
                "returncode": result.returncode,
                "stdout": stdout.decode("utf-8"),
                "stderr": stderr.decode("utf-8"),
                "success": result.returncode == 0,
            }

        except asyncio.TimeoutError:
            logger.error("Command timeout", command=" ".join(cmd), cwd=str(cwd))
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Command timeout",
                "success": False,
            }
        except Exception as e:
            logger.error(
                "Failed to run command",
                command=" ".join(cmd),
                cwd=str(cwd),
                error=str(e),
            )
            return {"returncode": -1, "stdout": "", "stderr": str(e), "success": False}

    async def check_file_exists(self, file_path: Path) -> bool:
        """
        Check if a file exists.

        Args:
            file_path: Path to check

        Returns:
            True if file exists
        """
        return file_path.exists() and file_path.is_file()

    async def get_changed_files(self, repo_path: Path) -> list[str]:
        """
        Get list of changed files in the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            List of changed file paths
        """
        try:
            cmd = ["git", "diff", "--name-only", "HEAD"]
            result = await self.run_command(cmd, repo_path)

            if result["success"]:
                changed_files = [
                    f.strip() for f in result["stdout"].split("\n") if f.strip()
                ]
                return changed_files
            else:
                return []

        except Exception as e:
            logger.error(
                "Failed to get changed files", repo_path=str(repo_path), error=str(e)
            )
            return []

    async def commit_changes(self, repo_path: Path, message: str) -> dict[str, Any]:
        """
        Commit changes to the repository.

        Args:
            repo_path: Path to the repository
            message: Commit message

        Returns:
            Commit result
        """
        try:
            # Configure git user (required for commits)
            await self.run_command(
                ["git", "config", "user.name", "Renovate PR Assistant"], repo_path
            )
            await self.run_command(
                ["git", "config", "user.email", "ai-code-assistant@example.com"],
                repo_path,
            )

            # Add all changes
            add_result = await self.run_command(["git", "add", "-A"], repo_path)
            if not add_result["success"]:
                return {"success": False, "error": "Failed to add changes"}

            # Check if there are any changes to commit
            status_result = await self.run_command(
                ["git", "status", "--porcelain"], repo_path
            )

            if not status_result["stdout"].strip():
                return {"success": True, "message": "No changes to commit"}

            # Commit changes
            commit_result = await self.run_command(
                ["git", "commit", "-m", message], repo_path
            )

            if commit_result["success"]:
                # Get commit SHA
                sha_result = await self.run_command(
                    ["git", "rev-parse", "HEAD"], repo_path
                )

                commit_sha = (
                    sha_result["stdout"].strip() if sha_result["success"] else None
                )

                return {"success": True, "commit_sha": commit_sha, "message": message}
            else:
                return {"success": False, "error": commit_result["stderr"]}

        except Exception as e:
            logger.error(
                "Failed to commit changes", repo_path=str(repo_path), error=str(e)
            )
            return {"success": False, "error": str(e)}

    async def push_changes(self, repo_path: Path, branch: str) -> dict[str, Any]:
        """
        Push changes to the remote repository.

        Args:
            repo_path: Path to the repository
            branch: Branch to push to

        Returns:
            Push result
        """
        try:
            cmd = ["git", "push", "origin", branch]
            result = await self.run_command(cmd, repo_path)

            if result["success"]:
                logger.info(
                    "Changes pushed successfully",
                    repo_path=str(repo_path),
                    branch=branch,
                )
                return {"success": True}
            else:
                logger.error(
                    "Failed to push changes",
                    repo_path=str(repo_path),
                    branch=branch,
                    error=result["stderr"],
                )
                return {"success": False, "error": result["stderr"]}

        except Exception as e:
            logger.error(
                "Failed to push changes",
                repo_path=str(repo_path),
                branch=branch,
                error=str(e),
            )
            return {"success": False, "error": str(e)}

    async def cleanup_repo(self, repo_path: Path) -> None:
        """
        Clean up repository directory.

        Args:
            repo_path: Path to clean up
        """
        try:
            if repo_path.exists():
                shutil.rmtree(repo_path)
                logger.info("Repository cleaned up", path=str(repo_path))
        except Exception as e:
            logger.error(
                "Failed to cleanup repository", path=str(repo_path), error=str(e)
            )

    async def fix_dependencies_workflow(
        self, repo_url: str, branch: str, pr_number: int
    ) -> dict[str, Any]:
        """
        Complete dependency fixing workflow.

        Args:
            repo_url: Repository URL
            branch: Branch to work on
            pr_number: Pull request number

        Returns:
            Workflow result
        """
        repo_path = None

        try:
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                repo_path = Path(temp_dir) / "repo"

                # Clone repository
                clone_success = await self.clone_repository(repo_url, repo_path, branch)
                if not clone_success:
                    return {"success": False, "error": "Failed to clone repository"}

                # Check if we can fix this repository
                can_fix = await self.can_fix(repo_path)
                if not can_fix:
                    return {"success": False, "error": "Cannot fix this repository"}

                # Validate tools
                tools_valid = await self.validate_tools()
                if not tools_valid:
                    return {"success": False, "error": "Required tools not available"}

                # Fix dependencies
                fix_result = await self.fix_dependencies(repo_path, branch)
                if not fix_result["success"]:
                    return fix_result

                # Get changed files
                changed_files = await self.get_changed_files(repo_path)

                if not changed_files:
                    return {"success": True, "message": "No changes needed"}

                # Commit changes
                commit_message = f"fix: update lock files for PR #{pr_number}"
                commit_result = await self.commit_changes(repo_path, commit_message)

                if not commit_result["success"]:
                    return {"success": False, "error": commit_result["error"]}

                # Push changes
                push_result = await self.push_changes(repo_path, branch)

                if not push_result["success"]:
                    return {"success": False, "error": push_result["error"]}

                return {
                    "success": True,
                    "changes": changed_files,
                    "commit_sha": commit_result.get("commit_sha"),
                    "message": "Dependencies fixed successfully",
                }

        except Exception as e:
            logger.error(
                "Dependency fixing workflow failed",
                repo_url=repo_url,
                branch=branch,
                pr_number=pr_number,
                error=str(e),
            )
            return {"success": False, "error": str(e)}

        finally:
            # Cleanup is handled by tempfile.TemporaryDirectory
            pass
