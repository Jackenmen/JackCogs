from typing import Optional, Sequence, Tuple, TypeVar

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition, is_done, renderer_height_is_known
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.key_binding.key_bindings import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer, HSplit
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import BaseStyle
from prompt_toolkit.widgets import RadioList, Label


_T = TypeVar("_T")


class GoToPrevious(Exception):
    """Raised to go back to previous prompt."""


class GoToNext(Exception):
    """Raised when application should go to next prompt."""


def radiolist_dialog(
    title: AnyFormattedText,
    values: Sequence[Tuple[_T, AnyFormattedText]],
    *,
    allow_previous: bool = True,
    allow_next: bool = False,
    style: Optional[BaseStyle] = None,
) -> _T:
    # Add exit key binding.
    bindings = KeyBindings()

    if allow_previous:
        @bindings.add("c-p")
        @bindings.add("c-u")
        def go_to_previous(event: KeyPressEvent) -> None:
            event.app.exit(exception=GoToPrevious)

    if allow_next:
        @bindings.add("c-n")
        def go_to_next(event: KeyPressEvent) -> None:
            event.app.exit(exception=GoToNext)

    @bindings.add("c-m")
    def exit_with_value(event: KeyPressEvent) -> None:
        event.app.exit(result=radio_list.current_value)

    @bindings.add("c-c")
    def keyboard_interrupt(event: KeyPressEvent) -> None:
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    radio_list = RadioList(values)
    radio_list.control.key_bindings.remove("enter")

    keybind_explanations = ["Press SPACE to mark", "ENTER to continue"]
    if allow_previous:
        keybind_explanations.append("Ctrl+p for previous prompt")
    if allow_next:
        keybind_explanations.append("Ctrl+n for next prompt")
    bottom_toolbar = ", ".join(keybind_explanations) + "."

    bottom_toolbar_container = ConditionalContainer(
        Window(
            FormattedTextControl(
                lambda: bottom_toolbar, style="class:bottom-toolbar.text"
            ),
            style="class:bottom-toolbar",
            dont_extend_height=True,
            height=Dimension(min=1),
        ),
        filter=(
            ~is_done
            & renderer_height_is_known
            & Condition(lambda: bottom_toolbar is not None)
        ),
    )

    application = Application(
        layout=Layout(HSplit([Label(title), radio_list, bottom_toolbar_container])),
        key_bindings=merge_key_bindings([load_key_bindings(), bindings]),
        mouse_support=True,
        style=style,
        full_screen=False,
    )

    return application.run()
