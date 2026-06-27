"""Подстановка плейсхолдеров в ComfyUI workflow: многострочный промт не должен ломать JSON."""


def test_workflow_substitution_escapes_multiline(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "WORKFLOWS_DIR", str(tmp_path))
    (tmp_path / "wf.json").write_text(
        '{"6":{"class_type":"CLIPTextEncode","inputs":{"text":"{{prompt}}","w":{{param.width}}}}}',
        encoding="utf-8",
    )
    from app.providers.comfyui import ComfyUIProvider
    p = ComfyUIProvider()
    ctx = {"prompt": 'line1\nline2 with "quotes"', "param": {"width": 1024}}
    wf = p._load_workflow("wf", ctx)  # внутри json.loads → бросит, если JSON битый
    assert wf["6"]["inputs"]["text"] == 'line1\nline2 with "quotes"'
    assert wf["6"]["inputs"]["w"] == 1024
