"""Focus guards for views updated while another activity is visible."""

from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import TabbedContent, TabPane


def is_active_view(widget: Widget) -> bool:
    """Use current tab state, not a hidden view's last rendered geometry."""
    if not widget.is_attached:
        return False
    for ancestor in widget.ancestors_with_self:
        if isinstance(ancestor, TabPane):
            try:
                tabs = ancestor.query_ancestor(TabbedContent)
            except NoMatches:
                continue
            if tabs.active != ancestor.id:
                return False
        if not ancestor.display:
            return False
    return True
