from __future__ import annotations

import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_mtime: Mapped[float] = mapped_column(Float, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False, default="local")

    # Perceptual hashes
    phash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dhash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Image metadata
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # EXIF fields
    exif_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    exif_camera_make: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exif_camera_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exif_gps_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exif_gps_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exif_focal_length: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exif_aperture: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exif_iso: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exif_exposure: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI fields
    ai_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    ai_description_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_tags_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_description_fi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_tags_fi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_colors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    ai_scene_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    indexed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    status_changed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=func.now()
    )

    # Relationships
    duplicate_group_memberships: Mapped[List["DuplicateGroupMember"]] = relationship(
        "DuplicateGroupMember", back_populates="image", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_images_phash", "phash"),
        Index("ix_images_dhash", "dhash"),
        Index("ix_images_exif_date", "exif_date"),
        Index("ix_images_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Image id={self.id} file_name={self.file_name!r} status={self.status!r}>"


class DuplicateGroup(Base):
    __tablename__ = "duplicate_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=func.now()
    )

    # Relationships
    members: Mapped[List["DuplicateGroupMember"]] = relationship(
        "DuplicateGroupMember", back_populates="group", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<DuplicateGroup id={self.id} match_type={self.match_type!r}>"


class DuplicateGroupMember(Base):
    __tablename__ = "duplicate_group_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("duplicate_groups.id"), nullable=False
    )
    image_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("images.id"), nullable=False
    )
    is_best: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_choice: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    group: Mapped["DuplicateGroup"] = relationship("DuplicateGroup", back_populates="members")
    image: Mapped["Image"] = relationship("Image", back_populates="duplicate_group_memberships")

    def __repr__(self) -> str:
        return f"<DuplicateGroupMember id={self.id} group_id={self.group_id} image_id={self.image_id}>"


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r} value={self.value!r}>"
