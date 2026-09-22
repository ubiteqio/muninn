"""Places: the towns and cities of GeoNames, to name where a medium was taken."""

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class Place(Base):
    """One place with at least 1,000 inhabitants, named in German where GeoNames knows how.

    Filled from the file the image build prepares (muninn.places.gazetteer). The generated
    PostGIS point "location" is only read by the SQL in muninn.places, so it is left out here.
    """

    __tablename__ = "places"

    #: GeoNames' own id, so a reload keeps every medium's place.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    population: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    #: Every name it may be searched by, lower case, its region's and country's included.
    keys: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
