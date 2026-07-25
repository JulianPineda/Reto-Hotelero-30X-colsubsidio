import pytest
from fastapi import HTTPException

from app.api import exports


@pytest.fixture
def export_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(exports, "BASE_EXPORT_DIR", tmp_path)
    return tmp_path


async def test_download_export_serves_existing_file(export_dir):
    file_path = export_dir / "PSL-ALMACEN-GENERAL_2026-07-24_morning_a1b2c3d4.csv"
    file_path.write_text("WAREHOUSE_CODE|ORACLE_CODE\n", encoding="utf-8")

    response = await exports.download_export(file_path.name, _operator=None)

    assert str(response.path) == str(file_path)
    assert response.media_type == "text/csv"


async def test_download_export_rejects_path_traversal(export_dir):
    with pytest.raises(HTTPException) as exc_info:
        await exports.download_export("../../../etc/passwd", _operator=None)

    assert exc_info.value.status_code == 400


async def test_download_export_404_when_file_missing(export_dir):
    with pytest.raises(HTTPException) as exc_info:
        await exports.download_export("does-not-exist.csv", _operator=None)

    assert exc_info.value.status_code == 404
