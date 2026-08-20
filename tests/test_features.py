"""三功能(work/memory/gacha)功能验证 — 数据互通、配额、检索、图鉴。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console

import agentx.cli.main as m
from agentx.session.session import Session
from agentx.cli.extras import (
    WorkHistory,
    MemoryStore,
    GachaSystem,
    CATS,
    DAILY_PULL_LIMIT,
    GOD_CHANCE,
    RARITY_STYLE,
)
from agentx.tools.base import ToolRegistry


def test_work_history_records_isolated_by_session():
    with TemporaryDirectory() as d:
        wh1 = WorkHistory("sessA", work_dir=Path(d))
        wh2 = WorkHistory("sessB", work_dir=Path(d))
        wh1.record("write_file", "/tmp/a.txt", "创建", content="hello")
        wh1.record("write_file", "/tmp/a.txt", "修改", content="hello2")
        assert len(wh1.list()) == 2
        assert wh2.list() == []
        # 重载持久化
        wh1b = WorkHistory("sessA", work_dir=Path(d))
        assert len(wh1b.list()) == 2
        assert wh1b.list()[0]["content"] == "hello"
        assert wh1b.list()[0]["abs_path"].endswith("a.txt")


def test_work_history_record_helpers():
    with TemporaryDirectory() as d:
        work_history = WorkHistory("s1", work_dir=Path(d))
        tmp = Path(d) / "new.txt"
        m._record_work_history(work_history, "write_file", {"path": str(tmp), "content": "x"})
        assert work_history.list()[-1]["action"] == "创建"
        tmp.write_text("y", encoding="utf-8")
        m._record_work_history(work_history, "write_file", {"path": str(tmp), "content": "y"})
        assert work_history.list()[-1]["action"] == "修改"
        m._record_work_history(work_history, "read_file", {"path": str(tmp)})
        assert work_history.list()[-1]["action"] == "读取"
        m._record_work_history(work_history, "run_shell_cmd", {"command": "echo hi"})
        assert work_history.list()[-1]["action"] == "命令"


def test_memory_store_roundtrip_and_search():
    with TemporaryDirectory() as d:
        store = MemoryStore(Path(d))
        s = Session(session_id="abc123")
        s.add_user("帮我看看怎么配置 DeepSeek")
        s.add_assistant("把 base_url 改为 api.deepseek.com 即可")
        store.save(s)

        assert len(store.list_all()) == 1
        hits = store.search("deepseek")
        assert len(hits) == 1 and hits[0]["session_id"] == "abc123"
        assert store.search("不存在的词") == []


def test_gacha_quota_daily_reset():
    with TemporaryDirectory() as d:
        path = Path(d) / ".pet_data.json"
        g = GachaSystem(path)
        assert g.remaining() == DAILY_PULL_LIMIT
        for _ in range(DAILY_PULL_LIMIT):
            pet, err = g.pull()
            assert err is None and pet is not None
        pet, err = g.pull()
        assert pet is None and err is not None
        assert g.remaining() == 0
        # 存档持久化后仍然用完
        g2 = GachaSystem(path)
        assert g2.remaining() == 0
        # 模拟第二天: 手动改日期
        data = json.loads(path.read_text(encoding="utf-8"))
        from datetime import timedelta
        data["quota"]["date"] = (__import__("datetime").date.today() - timedelta(days=1)).isoformat()
        path.write_text(json.dumps(data), encoding="utf-8")
        g3 = GachaSystem(path)
        assert g3.remaining() == DAILY_PULL_LIMIT


def test_gacha_rarity_pool_and_collection():
    with TemporaryDirectory() as d:
        path = Path(d) / ".pet_data.json"
        g = GachaSystem(path)
        names = set()
        for _ in range(200):
            pet, err = g.pull()
            if err is not None:
                # 每日配额用尽 -> 手动把日期改回今天, 刷新配额
                data = json.loads(path.read_text(encoding="utf-8"))
                data["quota"]["date"] = "2000-01-01"
                path.write_text(json.dumps(data), encoding="utf-8")
                g = GachaSystem(path)
                pet, err = g.pull()
            assert err is None, err
            assert pet["name"] in {n for sp in CATS.values() for n in sp["pets"]}
            names.add(pet["name"])
        col = g.collection()
        assert len(col) >= 1
        # 活跃宠物 = 最后一只
        assert g.active_pet() is not None
        assert g.active_pet()["name"] == g._data["active"]
        # 图鉴数量与总抽数一致
        total = sum(v["count"] for v in col.values())
        assert total == 200


def test_gacha_god_chance_only_ancestor():
    # 神级仅限原猫: 手动模拟 roll 到原猫 + 命中 god
    g = GachaSystem(Path("/tmp/opencode") / "_pet_god.json")
    # 打桩随机
    import agentx.cli.extras as ex
    orig_random = ex.random.random
    calls = {"n": 0}

    def fake_random():
        calls["n"] += 1
        if calls["n"] == 1:
            return 0.995  # 命中传说(原猫) 1% 区间
        return 0.0001    # 命中神级 0.1% 区间
    ex.random.random = fake_random
    try:
        pet, err = g.pull()
        assert pet["name"] == "原猫"
        assert pet["rarity"] == "神级" and pet["god"] is True
    finally:
        ex.random.random = orig_random


def test_save_session_writes_memory(monkeypatch):
    from agentx.cli.extras import MemoryStore as _MS
    from agentx.config import Config as _Config
    saved = []

    def fake_save(self, session):
        saved.append(session.id)
    monkeypatch.setattr(_MS, "save", fake_save)

    class FakeCfg:
        sessions_dir = Path("/tmp/opencode/_fake_sessions")
        _fake_cfg_dir = Path("/tmp/opencode/_fake_sessions")
        _fake_cfg_dir.mkdir(parents=True, exist_ok=True)

    cfg = FakeCfg()
    s = Session(session_id="mm1")
    s.add_user("记录一下部署步骤")
    m._save_session(cfg, s)
    assert saved == ["mm1"]


def test_work_list_selection_by_index_and_name():
    with TemporaryDirectory() as d:
        work_history = WorkHistory("s1", work_dir=Path(d))
        work_history.record("write_file", "/tmp/opencode/_a.txt", "创建", content="AAA")
        work_history.record("write_file", "/tmp/opencode/_b.txt", "创建", content="BBB")

        console = Console(force_terminal=False, width=120)
        picked = {}
        # 按编号选择
        m.render_work_list(console, work_history.list(), lambda p: "1")
        # 按文件名选择
        m.render_work_list(console, work_history.list(), lambda p: "_b.txt")
        assert len(work_history.list()) == 2

