"""抽卡皮肤应用验证: 抽到的宠物皮肤应能显示在界面宠物形象上。"""

from agentx.cli.ui import PetMascot
from agentx.cli.extras import GachaSystem


def test_active_pet_art_empty_when_no_pet(tmp_path):
    g = GachaSystem(path=tmp_path / "pet.json")
    assert g.active_pet_art() == ""


def test_active_pet_art_returns_skin_art(tmp_path):
    g = GachaSystem(path=tmp_path / "pet.json")
    g._data["active"] = "美短"
    g._data["collection"] = {
        "美短": {"count": 1, "first": "2026-08-27", "rarity": "非凡", "god": False}
    }
    art = g.active_pet_art()
    assert art
    assert "▒▓" in art


def test_pet_skin_applies_to_render(tmp_path):
    g = GachaSystem(path=tmp_path / "pet.json")
    g._data["active"] = "老虎"
    g._data["collection"] = {
        "老虎": {"count": 1, "first": "2026-08-27", "rarity": "史诗", "god": False}
    }
    pet = PetMascot("小智")
    pet.apply_skin(g.active_pet_art(), g.active_pet()["name"])

    panel = pet.render()
    assert "老虎" in str(panel.title)
    assert "王" in str(panel.renderable)


def test_pet_default_render_without_skin():
    pet = PetMascot("小智")
    pet.set_state("thinking")
    panel = pet.render()
    assert "🤔" in str(panel.renderable)
    assert "小智" in str(panel.title)


def test_apply_skin_empty_restores_default():
    pet = PetMascot("小智")
    pet.apply_skin("""[bold]fake[/bold]""", "老虎")
    assert "fake" in str(pet.render().renderable)
    pet.apply_skin("")
    assert "fake" not in str(pet.render().renderable)


def test_activate_switches_active_pet(tmp_path):
    g = GachaSystem(path=tmp_path / "pet.json")
    g._data["collection"] = {
        "英短": {"count": 2, "first": "2026-08-27", "rarity": "非凡", "god": False},
        "老虎": {"count": 1, "first": "2026-08-27", "rarity": "史诗", "god": False},
    }
    assert g.activate("老虎") is True
    assert g.active_pet()["name"] == "老虎"
    assert g.activate("不存在") is False
    assert g.active_pet()["name"] == "老虎"


def test_render_collection_returns_picked(tmp_path):
    from rich.console import Console
    from agentx.cli.extras import render_collection

    g = GachaSystem(path=tmp_path / "pet.json")
    g._data["collection"] = {
        "英短": {"count": 2, "first": "2026-08-27", "rarity": "非凡", "god": False},
        "老虎": {"count": 1, "first": "2026-08-27", "rarity": "史诗", "god": False},
    }
    picked = render_collection(Console(), g, ask=lambda _prompt: "2")
    assert picked == "老虎"
    picked2 = render_collection(Console(), g, ask=lambda _prompt: "")
    assert picked2 is None
    picked3 = render_collection(Console(), g, ask=lambda _prompt: "99")
    assert picked3 is None
