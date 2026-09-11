"""
Hover context for task lines.

Project, tags and friends never appear in the buffer text - GENERIC_TASK only
knows about description, priority, due and uuid - so there is nothing to
conceal. Instead the configured fields are rendered as Neovim virtual text on
the cursor line only, which leaves the wiki files on disk byte-identical.
"""

from __future__ import print_function

import vim  # pylint: disable=F0401

from taskwiki import errors
from taskwiki import regexp
from taskwiki import short
from taskwiki import util


NAMESPACE = 'taskwiki_hover'

DEFAULT_FIELDS = ('project', 'tags', 'due', 'urgency', 'uuid')

# Date only: the time component is not tracked at that granularity. Set
# g:taskwiki_hover_due_format to '%Y-%m-%d %H:%M' to include it.
DEFAULT_DUE_FORMAT = '%Y-%m-%d'


def _format_project(task, opts):
    project = task['project']
    return '~{0}'.format(project) if project else None


def _format_tags(task, opts):
    tags = task['tags']
    return ' '.join(['+{0}'.format(tag) for tag in tags]) if tags else None


def _timestamp_formatter(key, prefix):
    def formatter(task, opts):
        value = task[key]
        if not value:
            return None
        return '{0}:{1}'.format(prefix, value.strftime(opts['due_format']))

    return formatter


def _format_urgency(task, opts):
    urgency = task['urgency']
    return None if urgency is None else 'urg:{0:.1f}'.format(urgency)


def _format_uuid(task, opts):
    # Prefer the representation used on the task line itself, which carries
    # the 'H:' prefix for non-default TaskWarrior instances.
    value = opts.get('uuid_repr') or str(task['uuid'] or '')[:8]
    return '#{0}'.format(value) if value else None


def _format_status(task, opts):
    status = task['status']
    return 'status:{0}'.format(status) if status else None


def _format_annotations(task, opts):
    annotations = task['annotations']
    return 'notes:{0}'.format(len(annotations)) if annotations else None


def _format_depends(task, opts):
    depends = task['depends']
    return 'dep:{0}'.format(len(depends)) if depends else None


# field name -> (formatter, highlight group)
FIELDS = {
    'project': (_format_project, 'TaskWikiHoverProject'),
    'tags': (_format_tags, 'TaskWikiHoverTags'),
    'due': (_timestamp_formatter('due', 'due'), 'TaskWikiHoverDue'),
    'scheduled': (_timestamp_formatter('scheduled', 'sched'), 'TaskWikiHoverDue'),
    'urgency': (_format_urgency, 'TaskWikiHoverUrgency'),
    'uuid': (_format_uuid, 'TaskWikiHoverUuid'),
    'status': (_format_status, 'TaskWikiHoverStatus'),
    'annotations': (_format_annotations, 'TaskWikiHoverAnnotations'),
    'depends': (_format_depends, 'TaskWikiHoverStatus'),
}


def build_chunks(task, fields, due_format=DEFAULT_DUE_FORMAT, uuid_repr=None):
    """
    Build the (text, highlight group) pairs for the given task, in the order
    the fields were requested. Fields that are unset on the task contribute
    nothing, so no dangling separators are produced.
    """

    opts = {'due_format': due_format, 'uuid_repr': uuid_repr}
    chunks = []

    for field in fields:
        entry = FIELDS.get(field)

        # An unknown field name must not raise - this runs on cursor movement.
        if entry is None:
            continue

        formatter, highlight = entry

        try:
            text = formatter(task, opts)
        except (KeyError, TypeError, ValueError):
            continue

        if not text:
            continue

        # Separate the block from the task line, then the fields from each
        # other. The separator inherits the chunk's color, which is harmless.
        chunks.append(('  ' + text if not chunks else ' ' + text, highlight))

    return chunks


class HoverContext(object):
    """
    Renders the configured TaskWarrior fields of the task under the cursor as
    virtual text. Never modifies the buffer.
    """

    def __init__(self, cache):
        self.cache = cache

    @staticmethod
    def available():
        # Virtual text needs Neovim extmarks. In plain Vim this is a no-op.
        return hasattr(vim, 'api')

    @staticmethod
    def fields():
        configured = util.get_var('taskwiki_hover_fields')

        if configured is None:
            return list(DEFAULT_FIELDS)

        return [str(field) for field in configured]

    @staticmethod
    def namespace():
        # Idempotent: the same name always maps to the same namespace id.
        # Note pynvim's vim.api auto-prefixes 'nvim_', hence the bare name.
        return vim.api.create_namespace(NAMESPACE)

    def enabled(self):
        if util.get_var('taskwiki_disable_hover'):
            return False

        # Buffer-local switch flipped by :TaskWikiHoverToggle
        if util.get_var('taskwiki_hover_disabled',
                        vars_obj=vim.current.buffer.vars):
            return False

        return bool(self.fields())

    @errors.pretty_exception_handler
    def clear(self):
        if not self.available():
            return

        vim.api.buf_clear_namespace(0, self.namespace(), 0, -1)

    @errors.pretty_exception_handler
    def update(self):
        if not self.available():
            return

        self.clear()

        if not self.enabled():
            return

        line_number = util.get_current_line_number()

        # Read the live line rather than the buffer proxy, which may hold a
        # pre-edit snapshot.
        match = regexp.GENERIC_TASK.match(vim.current.line)

        if match is None:
            return

        uuid = match.group('uuid')

        if not uuid:
            return

        try:
            tw = self.cache.warriors[match.group('source') or 'default']
        except errors.TaskWikiException:
            return

        key = short.ShortUUID(uuid, tw)

        # Only serve what is already cached. Indexing the store on a miss
        # would spawn a TaskWarrior process on every cursor movement.
        if key not in self.cache.task:
            return

        chunks = build_chunks(
            self.cache.task[key],
            self.fields(),
            due_format=util.get_var('taskwiki_hover_due_format',
                                    DEFAULT_DUE_FORMAT),
            uuid_repr=key.vim_representation(self.cache),
        )

        if not chunks:
            return

        vim.api.buf_set_extmark(
            0,
            self.namespace(),
            line_number,
            0,
            {
                'virt_text': [list(chunk) for chunk in chunks],
                'virt_text_pos': 'eol',
                'hl_mode': 'combine',
            },
        )
