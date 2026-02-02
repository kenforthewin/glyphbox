"""Tests for authentication helpers and Phase 4 functionality."""

import os
from datetime import datetime

import pytest
from cryptography.fernet import Fernet

from src.persistence.models import RunRecord, UserRecord
from src.web.auth import (
    USERNAME_PATTERN,
    create_jwt,
    decode_jwt,
    decrypt_key,
    encrypt_key,
    generate_pkce_pair,
)

# === PKCE tests ===


class TestPKCE:
    def test_generates_verifier_and_challenge(self):
        verifier, challenge = generate_pkce_pair()
        assert len(verifier) > 20
        assert len(challenge) > 20
        assert verifier != challenge

    def test_challenge_is_sha256_of_verifier(self):
        import base64
        import hashlib

        verifier, challenge = generate_pkce_pair()
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert challenge == expected

    def test_different_each_time(self):
        pair1 = generate_pkce_pair()
        pair2 = generate_pkce_pair()
        assert pair1[0] != pair2[0]
        assert pair1[1] != pair2[1]


# === JWT tests ===


class TestJWT:
    SECRET = "test-secret-key-for-jwt-signing"

    def test_create_and_decode(self):
        token = create_jwt(42, self.SECRET, expiry_days=7)
        payload = decode_jwt(token, self.SECRET)
        assert payload is not None
        assert payload["sub"] == "42"

    def test_decode_bad_secret(self):
        token = create_jwt(42, self.SECRET)
        payload = decode_jwt(token, "wrong-secret")
        assert payload is None

    def test_decode_garbage_token(self):
        assert decode_jwt("not.a.jwt", self.SECRET) is None

    def test_decode_expired_token(self):
        token = create_jwt(42, self.SECRET, expiry_days=-1)
        payload = decode_jwt(token, self.SECRET)
        assert payload is None


# === Fernet encryption tests ===


class TestFernetEncryption:
    KEY = Fernet.generate_key().decode("utf-8")

    def test_encrypt_decrypt_roundtrip(self):
        original = "sk-or-v1-test-api-key-12345"
        encrypted = encrypt_key(original, self.KEY)
        assert encrypted != original
        decrypted = decrypt_key(encrypted, self.KEY)
        assert decrypted == original

    def test_decrypt_with_wrong_key(self):
        encrypted = encrypt_key("my-secret", self.KEY)
        wrong_key = Fernet.generate_key().decode("utf-8")
        with pytest.raises(Exception):
            decrypt_key(encrypted, wrong_key)


# === UserRecord tests ===


class TestUserRecord:
    def test_to_public_dict_omits_key(self):
        user = UserRecord(
            id=1,
            openrouter_id="or-123",
            display_name="user-or-12345",
            encrypted_openrouter_key="encrypted-secret",
            created_at=datetime(2026, 1, 15),
        )
        d = user.to_public_dict()
        assert d["id"] == 1
        assert d["openrouter_id"] == "or-123"
        assert d["display_name"] == "user-or-12345"
        assert "encrypted_openrouter_key" not in d


# === Username validation tests ===


class TestUsernameValidation:
    def test_valid_usernames(self):
        for name in ["abc", "user-123", "my_name", "A-B_c", "a" * 30]:
            assert USERNAME_PATTERN.match(name), f"{name} should be valid"

    def test_invalid_usernames(self):
        for name in ["ab", "a" * 31, "user name", "user@name", "user.name", ""]:
            assert not USERNAME_PATTERN.match(name), f"{name} should be invalid"


# === RunRecord tests ===


class TestRunRecord:
    def test_default_visibility_is_public(self):
        run = RunRecord(run_id="test", started_at=datetime(2026, 1, 1))
        assert run.visibility == "public"

    def test_to_dict_includes_username(self):
        run = RunRecord(
            run_id="test",
            started_at=datetime(2026, 1, 1),
            username="testuser",
        )
        d = run.to_dict()
        assert d["username"] == "testuser"
        assert d["visibility"] == "public"


# === Database tests (require Postgres) ===

TEST_DB_URL = os.environ.get(
    "NETHACK_TEST_DB_URL",
    "postgresql+asyncpg://nethack:nethack@localhost:5432/nethack_agent_test",
)

db_skip = pytest.mark.skipif(
    os.environ.get("SKIP_DB_TESTS", "").lower() in ("1", "true"),
    reason="Database tests skipped (SKIP_DB_TESTS=1)",
)


@db_skip
class TestUserManagement:
    @pytest.fixture
    async def engine(self):
        from sqlalchemy.ext.asyncio import create_async_engine

        from src.persistence.tables import metadata

        eng = create_async_engine(TEST_DB_URL)
        try:
            async with eng.begin() as conn:
                await conn.run_sync(metadata.drop_all)
                await conn.run_sync(metadata.create_all)
            yield eng
        finally:
            async with eng.begin() as conn:
                await conn.run_sync(metadata.drop_all)
            await eng.dispose()

    @pytest.fixture
    async def repo(self, engine):
        from src.persistence.postgres import PostgresRepository

        return PostgresRepository(engine)

    async def _create_user(self, repo, openrouter_id: str, name: str = "") -> UserRecord:
        display_name = name or f"user-{openrouter_id[:8]}"
        return await repo.upsert_user(
            openrouter_id=openrouter_id,
            display_name=display_name,
        )

    async def test_upsert_user_creates(self, repo):
        user = await repo.upsert_user("or-abc123", display_name="alice")
        assert user.id is not None
        assert user.openrouter_id == "or-abc123"
        assert user.display_name == "alice"

    async def test_upsert_user_updates_key(self, repo):
        await repo.upsert_user("or-abc123", encrypted_openrouter_key="key-v1")
        user = await repo.upsert_user("or-abc123", encrypted_openrouter_key="key-v2")
        assert user.encrypted_openrouter_key == "key-v2"

    async def test_get_user_by_id(self, repo):
        created = await repo.upsert_user("or-xyz")
        fetched = await repo.get_user(created.id)
        assert fetched is not None
        assert fetched.openrouter_id == "or-xyz"

    async def test_get_user_by_openrouter_id(self, repo):
        await repo.upsert_user("or-find-me")
        fetched = await repo.get_user_by_openrouter_id("or-find-me")
        assert fetched is not None
        assert fetched.openrouter_id == "or-find-me"

    async def test_get_user_not_found(self, repo):
        assert await repo.get_user(99999) is None
        assert await repo.get_user_by_openrouter_id("nope") is None

    async def test_update_display_name(self, repo):
        user = await self._create_user(repo, "or-rename", "old-name")
        updated = await repo.update_user_display_name(user.id, "new-name")
        assert updated.display_name == "new-name"

        # Verify persisted
        fetched = await repo.get_user(user.id)
        assert fetched.display_name == "new-name"

    async def test_update_display_name_not_found(self, repo):
        with pytest.raises(ValueError):
            await repo.update_user_display_name(99999, "name")


@db_skip
class TestListRunsPublic:
    """All runs are public — no visibility filtering."""

    @pytest.fixture
    async def engine(self):
        from sqlalchemy.ext.asyncio import create_async_engine

        from src.persistence.tables import metadata

        eng = create_async_engine(TEST_DB_URL)
        try:
            async with eng.begin() as conn:
                await conn.run_sync(metadata.drop_all)
                await conn.run_sync(metadata.create_all)
            yield eng
        finally:
            async with eng.begin() as conn:
                await conn.run_sync(metadata.drop_all)
            await eng.dispose()

    @pytest.fixture
    async def repo(self, engine):
        from src.persistence.postgres import PostgresRepository

        return PostgresRepository(engine)

    async def _seed_runs(self, repo):
        """Create test data: 2 users, 5 runs with different models/scores."""
        user_a = await repo.upsert_user("or-aaa", display_name="alice")
        user_b = await repo.upsert_user("or-bbb", display_name="bob")

        runs_data = [
            ("r1", user_a.id, "model-a", 100, 3, datetime(2026, 1, 1)),
            ("r2", user_a.id, "model-b", 500, 8, datetime(2026, 1, 2)),
            ("r3", user_b.id, "model-a", 200, 5, datetime(2026, 1, 3)),
            ("r4", user_b.id, "model-b", 1000, 12, datetime(2026, 1, 4)),
            ("r5", None, "model-a", 50, 1, datetime(2026, 1, 5)),
        ]
        for run_id, uid, model, score, depth, started_at in runs_data:
            await repo.create_run(
                RunRecord(
                    run_id=run_id,
                    started_at=started_at,
                    model=model,
                    provider="test",
                    user_id=uid,
                    final_score=score,
                    final_depth=depth,
                    status="stopped",
                )
            )
        return user_a, user_b

    async def test_list_all_runs(self, repo):
        await self._seed_runs(repo)
        runs = await repo.list_runs()
        assert len(runs) == 5

    async def test_list_runs_sort_recent(self, repo):
        await self._seed_runs(repo)
        runs = await repo.list_runs(sort_by="recent")
        assert runs[0].run_id == "r5"  # Most recent first

    async def test_list_runs_sort_score(self, repo):
        await self._seed_runs(repo)
        runs = await repo.list_runs(sort_by="score")
        assert runs[0].final_score == 1000

    async def test_list_runs_sort_depth(self, repo):
        await self._seed_runs(repo)
        runs = await repo.list_runs(sort_by="depth")
        assert runs[0].final_depth == 12

    async def test_list_runs_model_filter(self, repo):
        await self._seed_runs(repo)
        runs = await repo.list_runs(model_filter="model-a")
        assert len(runs) == 3
        assert all(r.model == "model-a" for r in runs)

    async def test_list_runs_user_filter(self, repo):
        user_a, _ = await self._seed_runs(repo)
        runs = await repo.list_runs(user_id=user_a.id)
        assert len(runs) == 2
        assert all(r.user_id == user_a.id for r in runs)

    async def test_list_runs_includes_username(self, repo):
        await self._seed_runs(repo)
        runs = await repo.list_runs()
        usernames = {r.username for r in runs}
        assert "alice" in usernames
        assert "bob" in usernames

    async def test_list_runs_null_user_has_empty_username(self, repo):
        await self._seed_runs(repo)
        runs = await repo.list_runs()
        no_user_runs = [r for r in runs if r.user_id is None]
        assert len(no_user_runs) == 1
        assert no_user_runs[0].username == ""


@db_skip
class TestLeaderboard:
    @pytest.fixture
    async def engine(self):
        from sqlalchemy.ext.asyncio import create_async_engine

        from src.persistence.tables import metadata

        eng = create_async_engine(TEST_DB_URL)
        try:
            async with eng.begin() as conn:
                await conn.run_sync(metadata.drop_all)
                await conn.run_sync(metadata.create_all)
            yield eng
        finally:
            async with eng.begin() as conn:
                await conn.run_sync(metadata.drop_all)
            await eng.dispose()

    @pytest.fixture
    async def repo(self, engine):
        from src.persistence.postgres import PostgresRepository

        return PostgresRepository(engine)

    async def test_leaderboard_by_score(self, repo):
        user = await repo.upsert_user("or-lead", display_name="leader")
        for i, (score, depth) in enumerate([(100, 3), (500, 5), (200, 8)]):
            await repo.create_run(
                RunRecord(
                    run_id=f"lb-{i}",
                    started_at=datetime(2026, 1, i + 1),
                    model="test",
                    user_id=user.id,
                    final_score=score,
                    final_depth=depth,
                    status="stopped",
                )
            )
        runs = await repo.get_leaderboard(metric="score")
        assert runs[0].final_score == 500
        assert runs[0].username == "leader"

    async def test_leaderboard_by_depth(self, repo):
        for i, depth in enumerate([3, 8, 5]):
            await repo.create_run(
                RunRecord(
                    run_id=f"lb-d-{i}",
                    started_at=datetime(2026, 1, i + 1),
                    model="test",
                    final_depth=depth,
                    status="stopped",
                )
            )
        runs = await repo.get_leaderboard(metric="depth")
        assert runs[0].final_depth == 8

    async def test_leaderboard_excludes_running(self, repo):
        await repo.create_run(
            RunRecord(
                run_id="running-1",
                started_at=datetime(2026, 1, 1),
                model="test",
                final_score=9999,
                status="running",
            )
        )
        await repo.create_run(
            RunRecord(
                run_id="stopped-1",
                started_at=datetime(2026, 1, 2),
                model="test",
                final_score=100,
                status="stopped",
            )
        )
        runs = await repo.get_leaderboard()
        assert len(runs) == 1
        assert runs[0].run_id == "stopped-1"


@db_skip
class TestDistinctModels:
    @pytest.fixture
    async def engine(self):
        from sqlalchemy.ext.asyncio import create_async_engine

        from src.persistence.tables import metadata

        eng = create_async_engine(TEST_DB_URL)
        try:
            async with eng.begin() as conn:
                await conn.run_sync(metadata.drop_all)
                await conn.run_sync(metadata.create_all)
            yield eng
        finally:
            async with eng.begin() as conn:
                await conn.run_sync(metadata.drop_all)
            await eng.dispose()

    @pytest.fixture
    async def repo(self, engine):
        from src.persistence.postgres import PostgresRepository

        return PostgresRepository(engine)

    async def test_list_distinct_models(self, repo):
        for i, model in enumerate(["model-b", "model-a", "model-b", "model-c"]):
            await repo.create_run(
                RunRecord(
                    run_id=f"dm-{i}",
                    started_at=datetime(2026, 1, i + 1),
                    model=model,
                )
            )
        models = await repo.list_distinct_models()
        assert models == ["model-a", "model-b", "model-c"]

    async def test_list_distinct_models_empty(self, repo):
        models = await repo.list_distinct_models()
        assert models == []
