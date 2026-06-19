"""数据库初始化 — 创建所有表并补齐轻量字段迁移。"""
from sqlalchemy import inspect, text

from app.db.session import engine, Base
import app.models  # noqa: F401 - 确保所有模型注册到 Base.metadata


def init_database():
    """创建所有 SQLAlchemy 模型对应的表"""
    Base.metadata.create_all(bind=engine)
    _ensure_draft_variant_columns()


def _ensure_draft_variant_columns():
    """v0.2-J 轻量迁移：旧 MySQL drafts 表补齐发布方案字段。"""
    inspector = inspect(engine)
    if "drafts" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("drafts")}
    columns = {
        "variant_name": "VARCHAR(255) NULL",
        "selected_title": "VARCHAR(255) NULL",
        "selected_cover_text": "VARCHAR(255) NULL",
        "body_variant_key": "VARCHAR(50) NULL",
        "body_variants": "JSON NULL",
        "content_type": "VARCHAR(100) NULL",
        "template_key": "VARCHAR(100) NULL",
        "theme_key": "VARCHAR(100) NULL",
        "max_card_count": "INT NULL",
        "generated_reason": "TEXT NULL",
    }
    missing = [(name, definition) for name, definition in columns.items() if name not in existing]
    if not missing:
        return
    with engine.begin() as conn:
        for name, definition in missing:
            conn.execute(text(f"ALTER TABLE drafts ADD COLUMN {name} {definition}"))


if __name__ == "__main__":
    init_database()
    print("数据库初始化完成")
