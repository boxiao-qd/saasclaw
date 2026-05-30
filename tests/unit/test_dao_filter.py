"""Tests for DAO user_account filter injection."""

import pytest
from app.dao.base import BaseDAO, BaseESDAO
from app.models.base import GLOBAL_SENTINEL
from sqlalchemy import or_


class TestBaseDAO:
    def test_filter_by_user_returns_correct_expression(self):
        """BaseDAO._filter_by_user should return Model.user_account == user_account."""
        from app.models.models import Session
        dao = BaseDAO(session_factory=None, user_account="user001")
        expr = dao._filter_by_user(Session)
        # Verify the expression right-hand value
        assert expr.right.value == "user001"

    def test_filter_user_or_global(self):
        """BaseDAO._filter_user_or_global should return a BooleanClauseList (OR expression)."""
        from app.models.models import Skill
        from sqlalchemy.sql.elements import BooleanClauseList
        dao = BaseDAO(session_factory=None, user_account="user001")
        expr = dao._filter_user_or_global(Skill)
        assert isinstance(expr, BooleanClauseList)

    def test_user_account_property(self):
        dao = BaseDAO(session_factory=None, user_account="user002")
        assert dao.user_account == "user002"


class TestBaseESDAO:
    def test_user_filter_returns_term_dict(self):
        dao = BaseESDAO(es_client=None, user_account="user001")
        filter_dict = dao._user_filter()
        assert filter_dict == {"term": {"user_account": "user001"}}