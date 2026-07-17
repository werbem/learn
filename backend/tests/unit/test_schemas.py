"""Unit tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.application.dto.report_dto import ReportCreateRequest


class TestReportCreateRequest:
    def test_valid_input(self) -> None:
        data = {
            "our_company": "公司A",
            "competitor_company": "公司B",
            "product": "产品X",
            "objective": "product_improvement",
        }
        req = ReportCreateRequest(**data)
        assert req.our_company == "公司A"
        assert req.objective == "product_improvement"

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            ReportCreateRequest(
                our_company="公司A",
                competitor_company="公司B",
            )

    def test_invalid_objective(self) -> None:
        with pytest.raises(ValidationError):
            ReportCreateRequest(
                our_company="A",
                competitor_company="B",
                product="C",
                objective="invalid_objective",
            )

    def test_empty_strings_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReportCreateRequest(
                our_company="",
                competitor_company="B",
                product="C",
                objective="product_improvement",
            )
