"""SQLAlchemy ORM models.

`user_id` is present but nullable from day one so the multi-user/account phase
(Phase 6) is a drop-in change rather than a schema migration.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Timezone-aware current UTC time (all timestamps are stored in UTC)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    url: Mapped[str] = mapped_column(String, nullable=False)
    retailer: Mapped[str] = mapped_column(String, default="", nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="", nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Latest observed values
    last_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_stock: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Previous values + change flags, for "what changed since last check" highlighting
    prev_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prev_stock: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    price_changed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stock_changed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    history: Mapped[List["PriceHistory"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="PriceHistory.captured_at",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Product id={self.id} name={self.name!r} price={self.last_price} {self.currency}>"


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stock: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="history")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<PriceHistory product_id={self.product_id} price={self.price} at={self.captured_at}>"
