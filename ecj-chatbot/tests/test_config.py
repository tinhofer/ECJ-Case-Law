"""Tests for the config module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from config import Config, get_config, set_data_dir, _config


class TestConfigDefaults:
    def test_default_subdirs(self):
        cfg = Config()
        assert cfg.cases_subdir == "cases"
        assert cfg.index_subdir == "index"

    def test_cases_dir_property(self, tmp_path):
        cfg = Config(data_dir=tmp_path)
        assert cfg.cases_dir == tmp_path / "cases"

    def test_index_dir_property(self, tmp_path):
        cfg = Config(data_dir=tmp_path)
        assert cfg.index_dir == tmp_path / "index"

    def test_default_search_settings(self):
        cfg = Config()
        assert cfg.n_results == 5
        assert cfg.relevance_threshold == 1.5
        assert cfg.enable_live_fallback is True

    def test_default_model_settings(self):
        cfg = Config()
        assert "multilingual-MiniLM" in cfg.embedding_model
        assert "claude" in cfg.llm_model

    def test_default_subject_areas(self):
        cfg = Config()
        assert isinstance(cfg.subject_areas, list)
        assert len(cfg.subject_areas) > 0
        assert "social policy" in cfg.subject_areas
        assert "data protection" in cfg.subject_areas
        assert "discrimination" in cfg.subject_areas
        assert "equal treatment" in cfg.subject_areas
        assert "fundamental rights" in cfg.subject_areas
        assert "artificial intelligence" in cfg.subject_areas

    def test_default_initial_year_is_2018(self):
        cfg = Config()
        assert cfg.initial_year == 2018

    def test_default_initial_limit_is_1000(self):
        cfg = Config()
        assert cfg.initial_limit == 1000


class TestEnsureDirectories:
    def test_creates_dirs(self, tmp_path):
        cfg = Config(data_dir=tmp_path / "new_data")
        cfg.ensure_directories()
        assert cfg.cases_dir.is_dir()
        assert cfg.index_dir.is_dir()

    def test_idempotent(self, tmp_path):
        cfg = Config(data_dir=tmp_path / "new_data")
        cfg.ensure_directories()
        cfg.ensure_directories()  # should not raise
        assert cfg.cases_dir.is_dir()


class TestIsCloudStorage:
    @pytest.mark.parametrize("path_fragment", [
        "OneDrive", "Google Drive", "googledrive", "Dropbox", "iCloud"
    ])
    def test_detects_cloud_paths(self, path_fragment):
        cfg = Config(data_dir=Path(f"/Users/test/{path_fragment}/EuGH"))
        assert cfg.is_cloud_storage() is True

    def test_local_path_not_cloud(self, tmp_path):
        cfg = Config(data_dir=tmp_path)
        assert cfg.is_cloud_storage() is False


class TestGetStatus:
    def test_returns_expected_keys(self, tmp_path):
        cfg = Config(data_dir=tmp_path)
        cfg.ensure_directories()
        status = cfg.get_status()
        assert "data_dir" in status
        assert "cases_count" in status
        assert "index_exists" in status
        assert "is_cloud_storage" in status

    def test_counts_json_files(self, populated_cases_dir, tmp_data_dir):
        cfg = Config(data_dir=tmp_data_dir)
        status = cfg.get_status()
        assert status["cases_count"] == 2

    def test_zero_cases_when_empty(self, tmp_data_dir):
        cfg = Config(data_dir=tmp_data_dir)
        status = cfg.get_status()
        assert status["cases_count"] == 0


class TestFromEnv:
    def test_picks_up_env_vars(self):
        env = {
            "ECJ_INITIAL_YEAR": "2018",
            "ECJ_EMBEDDING_MODEL": "custom-model",
            "ECJ_LLM_MODEL": "claude-opus-4-20250514",
            "ECJ_ENABLE_LIVE_FALLBACK": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = Config.from_env()
            assert cfg.initial_year == 2018
            assert cfg.embedding_model == "custom-model"
            assert cfg.llm_model == "claude-opus-4-20250514"
            assert cfg.enable_live_fallback is False

    def test_defaults_without_env_vars(self):
        env_keys = [
            "ECJ_INITIAL_YEAR", "ECJ_EMBEDDING_MODEL",
            "ECJ_LLM_MODEL", "ECJ_ENABLE_LIVE_FALLBACK",
        ]
        with patch.dict(os.environ, {}, clear=False):
            for key in env_keys:
                os.environ.pop(key, None)
            cfg = Config.from_env()
            assert cfg.initial_year == 2018
            assert cfg.enable_live_fallback is True


class TestSetDataDir:
    def test_updates_config(self, tmp_path):
        import config as config_module
        config_module._config = None  # reset singleton
        set_data_dir(tmp_path / "custom")
        cfg = get_config()
        assert cfg.data_dir == tmp_path / "custom"
        config_module._config = None  # cleanup
