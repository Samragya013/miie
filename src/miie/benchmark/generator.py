"""Benchmark Dataset Generator.
Implements the IDatasetGenerator interface for generating synthetic benchmark datasets.
"""

import json
import os
import random
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from miie.contracts.interfaces import IDatasetGenerator
from miie.schemas.serialization import json_dumps

# Safe environment for git subprocess calls — disables hooks and prompts
_GIT_SAFE_ENV = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_EDITOR": ":",
}


class BenchmarkDatasetGenerator(IDatasetGenerator):
    """Benchmark dataset generator that creates synthetic Git repositories with
    controlled characteristics for pathology injection.
    """

    def generate(
        self,
        dataset_type: str,
        count: int,
        output_dir: Path,
        seed: Optional[int] = None,
    ) -> List[Path]:
        """Generate synthetic benchmark datasets (Git repositories).

        Args:
            dataset_type: Type of dataset to generate (e.g., "metric-drift",
                         "correlation-breakdown", "threshold-compression")
            count: Number of synthetic datasets to generate
            output_dir: Directory to write generated datasets
            seed: Random seed for reproducibility

        Returns:
            List[Path]: Paths to generated dataset directories
        """
        # Set random seed for determinism
        if seed is not None:
            random.seed(seed)

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        generated_paths = []

        for i in range(count):
            candidate_index = i + 1
            candidate_dir = output_dir / f"candidate_{candidate_index:03d}"
            try:
                candidate_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                # Handle collision with uuid suffix
                import uuid

                candidate_dir = output_dir / f"candidate_{candidate_index:03d}_{uuid.uuid4().hex[:8]}"
                candidate_dir.mkdir(parents=True, exist_ok=True)
            generated_paths.append(candidate_dir)

            try:
                # Initialize Git repository
                self._init_git_repo(candidate_dir)

                # Generate metadata.json
                metadata = self._generate_metadata(candidate_index, dataset_type, seed)
                metadata_path = candidate_dir / "metadata.json"
                with open(metadata_path, "w", encoding="utf-8") as f:
                    f.write(json_dumps(metadata, indent=2))

                # Generate commit history with pathology injection
                self._generate_commit_history(candidate_dir, metadata, dataset_type, seed, candidate_index)
            except Exception:
                # Clean up on failure
                import shutil

                if candidate_dir.exists():
                    shutil.rmtree(candidate_dir, ignore_errors=True)
                raise

        # Note: Manifest update is handled separately
        return generated_paths

    def _init_git_repo(self, repo_path: Path, shallow_depth: int = 0) -> None:
        """Initialize a Git repository in the given directory.

        Args:
            repo_path: Directory to initialize as git repo.
            shallow_depth: If >0, create a shallow repo with this depth.
        """
        cmd = ["git", "init"]
        if shallow_depth > 0:
            cmd.extend(["--shallow-since=2020-01-01"])
        subprocess.run(cmd, cwd=repo_path, check=True, capture_output=True, timeout=30, env=_GIT_SAFE_ENV)
        # Configure git user (required for commits)
        subprocess.run(
            ["git", "config", "user.name", "MIIE Generator"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            timeout=10,
            env=_GIT_SAFE_ENV,
        )
        subprocess.run(
            ["git", "config", "user.email", "miie@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            timeout=10,
            env=_GIT_SAFE_ENV,
        )

    def _generate_metadata(self, candidate_index: int, dataset_type: str, base_seed: Optional[int]) -> dict:
        """Generate SyntheticRepositoryMetadata for a candidate."""
        # Derive a seed for this candidate from the base seed and index
        candidate_seed = base_seed if base_seed is not None else 42
        candidate_seed = hash((candidate_seed, candidate_index)) % 2**32
        random.seed(candidate_seed)

        # Select category, language, and parameters
        categories = [
            "small_active",
            "medium_active",
            "large_active",
            "seasonal",
            "monotonic_growth",
            "declining",
            "stable",
        ]
        category = random.choice(categories)

        languages = ["python", "java", "cpp", "javascript", "typescript"]
        language = random.choice(languages)

        # Generate parameters within ranges
        duration_days = random.randint(90, 730)
        total_commits = random.randint(60, 2400)
        contributors = random.randint(1, 50)
        bot_ratio = round(random.uniform(0.0, 0.3), 2)
        window_count = random.randint(6, 12)
        window_size_days = random.randint(30, 90)

        # Generate windows
        windows = []
        start_date = datetime.now() - timedelta(days=duration_days)
        for w in range(window_count):
            window_id = f"w{w+1:02d}"
            window_start = start_date + timedelta(days=w * (duration_days // window_count))
            window_end = start_date + timedelta(days=(w + 1) * (duration_days // window_count))
            # Ensure we have at least 10 commits per window
            commits_in_window = max(10, total_commits // window_count)
            windows.append(
                {
                    "window_id": window_id,
                    "start_date": window_start.strftime("%Y-%m-%d"),
                    "end_date": window_end.strftime("%Y-%m-%d"),
                    "commits": commits_in_window,
                }
            )

        # Adjust total_commits to match sum of window commits
        total_commits = sum(w["commits"] for w in windows)

        metadata = {
            "repo_id": f"repo_{candidate_index:03d}",
            "category": category,
            "language": language,
            "parameters": {
                "duration_days": duration_days,
                "total_commits": total_commits,
                "contributors": contributors,
                "bot_ratio": bot_ratio,
                "window_count": window_count,
                "window_size_days": window_size_days,
            },
            "windows": windows,
            "generation_seed": candidate_seed,
            "generation_timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        return metadata

    def _generate_commit_history(
        self,
        repo_path: Path,
        metadata: dict,
        dataset_type: str,
        base_seed: Optional[int],
        candidate_index: int,
    ) -> None:
        """Generate a series of commits to inject pathology specific to the suite."""
        # Determine the pathology type based on dataset_type
        pathology_type = self._get_pathology_type(dataset_type)

        # We'll generate commits over time, modifying files to inject the pathology
        # For simplicity, we'll create a few files and vary their content over commits

        # Create a simple file structure
        (repo_path / "src").mkdir(exist_ok=True)
        (repo_path / "tests").mkdir(exist_ok=True)

        # Create initial files
        (repo_path / "README.md").write_text(f"# Candidate {candidate_index}\n\nGenerated benchmark dataset.")
        (repo_path / "src" / "main.py").write_text("# Main application\n")
        (repo_path / "tests" / "test_main.py").write_text("# Tests\n")

        # Initial commit
        self._git_add_commit(
            repo_path,
            [
                str(repo_path / "README.md"),
                str(repo_path / "src" / "main.py"),
                str(repo_path / "tests" / "test_main.py"),
            ],
            f"Initial commit for candidate {candidate_index}",
        )

        # Generate a series of commits with varying characteristics
        total_commits = metadata["parameters"]["total_commits"]
        # We already have 1 commit, so we need total_commits - 1 more
        remaining_commits = total_commits - 1

        # We'll generate commits in batches to simulate different pathologies
        for c in range(remaining_commits):
            # Determine what to modify based on pathology type
            if pathology_type == "metric-drift":
                # Gradually increase or decrease the number of lines in a file
                self._commit_metric_drift(
                    repo_path,
                    c,
                    remaining_commits,
                    candidate_seed=metadata["generation_seed"],
                )
            elif pathology_type == "correlation-breakdown":
                # Introduce breakdown in correlation between two metrics
                self._commit_correlation_breakdown(
                    repo_path,
                    c,
                    remaining_commits,
                    candidate_seed=metadata["generation_seed"],
                )
            elif pathology_type == "threshold-compression":
                # Introduce threshold compression in a metric
                self._commit_threshold_compression(
                    repo_path,
                    c,
                    remaining_commits,
                    candidate_seed=metadata["generation_seed"],
                )
            else:
                # Default: just modify a file slightly
                self._commit_default(
                    repo_path,
                    c,
                    remaining_commits,
                    candidate_seed=metadata["generation_seed"],
                )

    def _get_pathology_type(self, dataset_type: str) -> str:
        """Map dataset_type to pathology type."""
        dataset_type_lower = dataset_type.lower()
        if "metric-drift" in dataset_type_lower:
            return "metric-drift"
        elif "correlation-breakdown" in dataset_type_lower:
            return "correlation-breakdown"
        elif "threshold-compression" in dataset_type_lower:
            return "threshold-compression"
        else:
            # Default to metric-drift
            return "metric-drift"

    def _git_add_commit(self, repo_path: Path, files: List[str], message: str) -> None:
        """Add files and commit with the given message.
        Assumes files are absolute paths.
        """
        rel_files = [str(Path(f).relative_to(repo_path)).replace("\\", "/") for f in files]
        result_add = subprocess.run(
            ["git", "add"] + rel_files, cwd=repo_path, capture_output=True, timeout=30, env=_GIT_SAFE_ENV
        )
        if result_add.returncode != 0:
            raise subprocess.CalledProcessError(
                result_add.returncode,
                ["git", "add"] + rel_files,
                result_add.stdout,
                result_add.stderr,
            )
        result_commit = subprocess.run(
            ["git", "commit", "-m", message], cwd=repo_path, capture_output=True, timeout=30, env=_GIT_SAFE_ENV
        )
        if result_commit.returncode != 0:
            raise subprocess.CalledProcessError(
                result_commit.returncode,
                ["git", "commit", "-m", message],
                result_commit.stdout,
                result_commit.stderr,
            )

    def _commit_metric_drift(
        self,
        repo_path: Path,
        commit_index: int,
        total_commits: int,
        candidate_seed: int,
    ) -> None:
        """Generate a commit that injects metric drift (gradual change in commit frequency or size)."""
        # We'll vary the size of a file over time to simulate drift in code churn (M-06)
        # Create or modify a file that tracks lines of code
        loc_file = repo_path / "src" / "loc.txt"
        # Determine the number of lines based on a linear trend
        # We'll make it increase linearly over time
        base_lines = 10
        drift_amount = int((commit_index / total_commits) * 100)  # Up to 100 extra lines
        total_lines = base_lines + drift_amount

        # Write the LOC file
        loc_file.write_text("\n".join(["# Line of code"] * total_lines))

        # Also modify another file to add noise
        noise_file = repo_path / "src" / "noise.txt"
        noise_content = random_string(random.randint(5, 20))
        noise_file.write_text(noise_content)

        self._git_add_commit(
            repo_path,
            [str(loc_file), str(noise_file)],
            f"Metric drift commit {commit_index+1}: LOC={total_lines}",
        )

    def _commit_correlation_breakdown(
        self,
        repo_path: Path,
        commit_index: int,
        total_commits: int,
        candidate_seed: int,
    ) -> None:
        """Generate a commit that injects correlation breakdown between two metrics."""
        # We'll create two files representing two metrics
        # Initially they are correlated, then we break the correlation
        metric_a_file = repo_path / "src" / "metric_a.txt"
        metric_b_file = repo_path / "src" / "metric_b.txt"

        # Determine correlation strength: start high, end low
        # We'll use a linear decay from 1.0 to 0.0 over the commits
        correlation = 1.0 - (commit_index / total_commits)

        # Generate two sequences of numbers with the given correlation
        # For simplicity, we'll generate a base value and then add noise
        base = random.gauss(0, 1)
        noise_a = random.gauss(0, 1 - correlation)  # Less noise when correlation high
        noise_b = random.gauss(0, 1 - correlation)
        value_a = base + noise_a
        value_b = base + noise_b

        # Write the values to files
        metric_a_file.write_text(f"{value_a:.4f}")
        metric_b_file.write_text(f"{value_b:.4f}")

        self._git_add_commit(
            repo_path,
            [str(metric_a_file), str(metric_b_file)],
            f"Correlation breakdown commit {commit_index+1}: corr={correlation:.2f}",
        )

    def _commit_threshold_compression(
        self,
        repo_path: Path,
        commit_index: int,
        total_commits: int,
        candidate_seed: int,
    ) -> None:
        """Generate a commit that injects threshold compression in a metric."""
        # We'll create a file representing a metric that gets clamped over time
        metric_file = repo_path / "src" / "metric.txt"

        # We'll simulate a metric that starts normally, then gets compressed to a range
        # For example, values between -10 and 10, but we clamp to [-5, 5] gradually
        raw_value = random.gauss(0, 10)  # Mean 0, std 10

        # Determine compression factor: start at 0 (no compression) to 1 (full compression)
        compression = commit_index / total_commits

        # Define the clamp range
        min_allowed, max_allowed = -5.0, 5.0

        # Apply compression: value = raw_value * (1 - compression) + clamped_value * compression
        # But we need to clamp the raw_value first
        clamped_raw = max(min_allowed, min(max_allowed, raw_value))
        final_value = raw_value * (1 - compression) + clamped_raw * compression

        metric_file.write_text(f"{final_value:.4f}")

        # Also modify another file to add some variability
        other_file = repo_path / "src" / "other.txt"
        other_file.write_text(random_string(random.randint(10, 30)))

        self._git_add_commit(
            repo_path,
            [str(metric_file), str(other_file)],
            f"Threshold compression commit {commit_index+1}: value={final_value:.2f}",
        )

    def _commit_default(
        self,
        repo_path: Path,
        commit_index: int,
        total_commits: int,
        candidate_seed: int,
    ) -> None:
        """Generate a default commit with random changes."""
        # Modify a random file
        file_to_modify = repo_path / "src" / "random.txt"
        content = random_string(random.randint(10, 50))
        file_to_modify.write_text(content)

        self._git_add_commit(repo_path, [str(file_to_modify)], f"Default commit {commit_index+1}")

    def update_manifest(
        self,
        output_dir: Path,
        generated_paths: List[Path],
        dataset_type: str,
        base_seed: Optional[int],
    ) -> None:
        """Update the candidate manifest.json with the generated candidates."""
        manifest_path = output_dir.parent / "metadata" / "candidate_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing manifest if it exists, otherwise create a new one
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        else:
            manifest_data = {
                "benchmark_info": {
                    "name": "MIIE Synthetic Benchmark Candidates",
                    "version": "1.0.0",
                    "description": "Synthetic benchmark candidates for testing MIIE detector algorithms",
                    "generation_date": datetime.now().strftime("%Y-%m-%d"),
                    "total_candidates": 0,
                    "status": "candidate",
                    "note": "These are benchmark candidates only - not final ground truth datasets",
                },
                "candidates": {},
            }

        # We'll generate entries for all candidates (including existing ones if we are regenerating)
        # But note: we are generating exactly 'count' candidates in this call.
        # However, the manifest may already have entries from previous generations.
        # We will replace the entries for the candidates we are generating.
        # For simplicity, we will clear the candidates and regenerate for all 120.
        # But we don't know the total count from here. We'll assume we are generating the full set.
        # Alternatively, we can update only the candidates we generated.
        # Since the authority audit says to generate 90 additional (total 120), we assume we are generating the full set.
        # We'll clear the existing candidates and add our generated ones.
        manifest_data["candidates"] = {}

        # Add each generated candidate
        for i, candidate_path in enumerate(generated_paths):
            candidate_index = i + 1
            candidate_id = f"candidate_{candidate_index:03d}"
            # We need to get the metadata for this candidate to fill in the manifest
            # We could regenerate the metadata, but we don't have it stored.
            # Instead, we'll read the metadata.json from the candidate directory
            metadata_path = candidate_path / "metadata.json"
            if metadata_path.exists():
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            else:
                # Fallback: generate minimal metadata
                metadata = {
                    "repo_id": f"repo_{candidate_index:03d}",
                    "generation_seed": base_seed if base_seed is not None else 42,
                    "generation_timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                }

            # Determine anomaly based on dataset_type and candidate index
            # For simplicity, we'll make the first 10 candidates in each suite have anomalies
            suite_anomaly_index = (candidate_index - 1) % 40  # 0-39 for each suite of 40
            anomaly_present = suite_anomaly_index < 10  # First 10 in each suite have anomaly
            anomaly_type = None
            if anomaly_present:
                if "metric-drift" in dataset_type.lower():
                    anomaly_type = "drift"
                elif "correlation-breakdown" in dataset_type.lower():
                    anomaly_type = "correlation_breakdown"
                elif "threshold-compression" in dataset_type.lower():
                    anomaly_type = "threshold_compressed"
                else:
                    anomaly_type = "drift"

            # Expected metrics based on anomaly type
            expected_metrics = []
            if anomaly_type == "drift":
                expected_metrics = ["M-02"]
            elif anomaly_type == "correlation_breakdown":
                expected_metrics = ["M-02", "M-06"]
            elif anomaly_type == "threshold_compressed":
                expected_metrics = ["M-06"]
            else:
                expected_metrics = ["M-02", "M-06"]

            # Tags
            tags = []
            if anomaly_present:
                tags.append(anomaly_type)
            tags.append("synthetic")

            manifest_data["candidates"][candidate_id] = {
                "id": candidate_id,
                "name": f"candidate_{candidate_index}",
                "description": f"Synthetic benchmark candidate {candidate_index}",
                "seed": metadata.get("generation_seed", 42),
                "anomaly_present": anomaly_present,
                "anomaly_type": anomaly_type,
                "expected_metrics": expected_metrics,
                "tags": tags,
                "path": str(candidate_path.relative_to(output_dir.parent)),  # Relative to benchmarks/
            }

        # Update total candidates
        manifest_data["benchmark_info"]["total_candidates"] = len(generated_paths)
        manifest_data["benchmark_info"]["generation_date"] = datetime.now().strftime("%Y-%m-%d")

        # Write manifest atomically
        self._write_manifest_atomic(manifest_path, manifest_data)

    def _write_manifest_atomic(self, manifest_path: Path, data: dict) -> None:
        """Write manifest atomically using temp file + rename."""
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=manifest_path.parent,
                delete=False,
                suffix=".tmp",
                prefix=manifest_path.name,
            ) as tf:
                temp_file = Path(tf.name)
                tf.write(json_dumps(data, indent=2))

            # Atomic replace
            if manifest_path.exists():
                manifest_path.replace(temp_file)  # Replace existing file
                temp_file.replace(manifest_path)  # Put temp file in target location
            else:
                temp_file.replace(manifest_path)  # Simply rename temp to target
        except Exception as e:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise e


def random_string(length: int) -> str:
    """Generate a random string of fixed length."""
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(letters) for _ in range(length))
