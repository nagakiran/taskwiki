# -*- coding: utf-8 -*-
from datetime import datetime
from tests.base import MockVim
import sys


class MockTask(dict):
    """
    Stands in for a tasklib Task: unset attributes read back as None rather
    than raising, which is what the formatters rely on.
    """

    def __missing__(self, key):
        return None


class TestHoverChunks(object):
    def setup_method(self, method):
        self.mockvim = MockVim()
        sys.modules['vim'] = self.mockvim
        from taskwiki import hover
        self.hover = hover

    def teardown_method(self, method):
        self.mockvim.reset()

    def build(self, task, fields, **kwargs):
        return self.hover.build_chunks(task, fields, **kwargs)

    def texts(self, chunks):
        return [text for text, _ in chunks]

    def test_project(self):
        task = MockTask(project='self.finance')
        assert self.build(task, ['project']) == [
            ('  ~self.finance', 'TaskWikiHoverProject')]

    def test_tags(self):
        task = MockTask(tags=['tax', 'itr'])
        assert self.build(task, ['tags']) == [
            ('  +tax +itr', 'TaskWikiHoverTags')]

    def test_urgency(self):
        task = MockTask(urgency=12.345)
        assert self.build(task, ['urgency']) == [
            ('  urg:12.3', 'TaskWikiHoverUrgency')]

    def test_uuid_from_task(self):
        task = MockTask(uuid='0123abcd-4567-89ef-0123-456789abcdef')
        assert self.build(task, ['uuid']) == [
            ('  #0123abcd', 'TaskWikiHoverUuid')]

    def test_uuid_repr_wins(self):
        # Non-default TaskWarrior instances carry the 'H:' prefix on the line.
        task = MockTask(uuid='0123abcd-4567-89ef-0123-456789abcdef')
        chunks = self.build(task, ['uuid'], uuid_repr='S:0123abcd')
        assert chunks == [('  #S:0123abcd', 'TaskWikiHoverUuid')]

    def test_due_is_date_only_by_default(self):
        task = MockTask(due=datetime(2026, 6, 12, 23, 59))
        assert self.build(task, ['due']) == [
            ('  due:2026-06-12', 'TaskWikiHoverDue')]

    def test_due_format_can_include_time(self):
        task = MockTask(due=datetime(2026, 6, 12, 23, 59))
        chunks = self.build(task, ['due'], due_format='%Y-%m-%d %H:%M')
        assert chunks == [('  due:2026-06-12 23:59', 'TaskWikiHoverDue')]

    def test_scheduled(self):
        task = MockTask(scheduled=datetime(2026, 6, 10, 0, 0))
        assert self.build(task, ['scheduled']) == [
            ('  sched:2026-06-10', 'TaskWikiHoverDue')]

    def test_annotations_and_depends_are_counts(self):
        task = MockTask(annotations=['a', 'b', 'c'], depends=set(['x', 'y']))
        assert self.texts(self.build(task, ['annotations', 'depends'])) == [
            '  notes:3', ' dep:2']

    def test_status(self):
        task = MockTask(status='waiting')
        assert self.build(task, ['status']) == [
            ('  status:waiting', 'TaskWikiHoverStatus')]

    def test_order_follows_config_not_field_table(self):
        task = MockTask(project='home', tags=['now'], urgency=1.0)
        assert self.texts(self.build(task, ['urgency', 'tags', 'project'])) == [
            '  urg:1.0', ' +now', ' ~home']

    def test_unset_fields_leave_no_dangling_separator(self):
        # No project, no tags: the first rendered chunk still gets the
        # two-space lead-in that separates the block from the task line.
        task = MockTask(urgency=3.0)
        assert self.texts(self.build(task, ['project', 'tags', 'urgency'])) == [
            '  urg:3.0']

    def test_empty_values_are_skipped(self):
        task = MockTask(project='', tags=[], annotations=[], depends=set())
        assert self.build(
            task, ['project', 'tags', 'annotations', 'depends']) == []

    def test_zero_urgency_is_still_rendered(self):
        # 0.0 is falsy but meaningful, unlike an empty project.
        task = MockTask(urgency=0.0)
        assert self.build(task, ['urgency']) == [
            ('  urg:0.0', 'TaskWikiHoverUrgency')]

    def test_unknown_field_is_skipped_not_raised(self):
        task = MockTask(project='home')
        assert self.texts(self.build(task, ['bogus', 'project'])) == ['  ~home']

    def test_no_fields_yields_no_chunks(self):
        assert self.build(MockTask(project='home'), []) == []

    def test_default_fields_used_when_unconfigured(self):
        assert self.hover.HoverContext.fields() == list(
            self.hover.DEFAULT_FIELDS)

    def test_configured_fields_are_honoured(self):
        self.mockvim.vars.update({'taskwiki_hover_fields': ['project', 'tags']})
        assert self.hover.HoverContext.fields() == ['project', 'tags']

    def test_unavailable_without_neovim_api(self):
        # Plain Vim has no vim.api, so the display must silently no-op.
        assert self.hover.HoverContext.available() is False
