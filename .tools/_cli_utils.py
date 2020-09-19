import keyword
import re
from pathlib import Path
from typing import List, Literal, Optional, Sequence, Tuple, TypeVar, Union, overload

from prompt_toolkit import prompt as real_prompt
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.document import Document
from prompt_toolkit.filters import (
    Always,
    Condition,
    Filter,
    emacs_insert_mode,
    in_paste_mode,
    is_done,
    renderer_height_is_known,
)
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.key_binding.bindings.named_commands import get_by_name
from prompt_toolkit.key_binding.key_bindings import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer, HSplit
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit.widgets import CheckboxList, Label, RadioList


__all__ = (
    "GoToLast",
    "GoToNext",
    "GoToPrevious",
    "NonEmptyValidator",
    "PythonIdentifierValidator",
    "TagsValidator",
    "dialoglist",
    "not_empty",
    "prompt",
)


ROOT_PATH = Path(__file__).absolute().parent.parent
_T = TypeVar("_T")


class PythonIdentifierValidator(Validator):
    def validate(self, document: Document) -> None:
        text = document.text
        if not text.isidentifier() or keyword.iskeyword(text):
            raise ValidationError(
                message="This input must be a valid Python identifier."
            )


class PackageNameValidator(PythonIdentifierValidator):
    def validate(self, document: Document) -> None:
        super().validate(document)
        text = document.text
        if not text.islower():
            raise ValidationError(message="Package name must be lower-case.")

        pkg_dir = ROOT_PATH / text
        if pkg_dir.exists():
            raise ValidationError(message="Package with this name already exists.")


class TagsValidator(Validator):
    PATTERN = re.compile(r"[\w ]*")

    def validate(self, document: Document) -> None:
        text = document.text
        if self.PATTERN.fullmatch(text) is None:
            raise ValidationError(
                message="Tags can only contain alphanumeric characters."
            )
        tags = text.split()
        if not tags:
            raise ValidationError(message="You need to add at least one tag.")


class NonEmptyValidator(Validator):
    def validate(self, document: Document) -> None:
        text = document.text
        if not text:
            raise ValidationError(message="This input cannot be empty.")


class GoToPrevious(Exception):
    """Raised to go back to previous prompt."""


class GoToNext(Exception):
    """Raised when application should go to next prompt."""


class GoToLast(Exception):
    """Raised when application should go to last prompt."""


@Condition
def _is_returnable() -> bool:
    return get_app().current_buffer.is_returnable


def _get_basic_keybindings(
    *, allow_previous: bool = True, allow_next: bool = False
) -> KeyBindings:
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

        @bindings.add("c-l")
        @bindings.add("c-e")
        def go_to_last(event: KeyPressEvent) -> None:
            event.app.exit(exception=GoToLast)

    return bindings


def _get_bottom_toolbar_text(
    prepend_list: List[str] = [],
    *,
    allow_previous: bool = True,
    allow_next: bool = False,
) -> str:
    keybind_explanations = prepend_list + ["ENTER to continue"]
    if allow_previous:
        keybind_explanations.append("Ctrl+p for previous prompt")
    if allow_next:
        keybind_explanations.append("Ctrl+n/Ctrl+l for next/last prompt")
    return f"\nPress {', '.join(keybind_explanations)}."


def _get_bottom_toolbar_container(
    prepend_list: List[str] = [],
    *,
    bottom_toolbar: str = "",
    allow_previous: bool = True,
    allow_next: bool = False,
):
    bottom_toolbar += _get_bottom_toolbar_text(
        prepend_list, allow_previous=allow_previous, allow_next=allow_next
    )

    return ConditionalContainer(
        Window(
            FormattedTextControl(lambda: bottom_toolbar, style="class:bottom-toolbar.text"),
            style="class:bottom-toolbar",
            dont_extend_height=True,
            height=Dimension(min=1),
        ),
        filter=(
            ~is_done & renderer_height_is_known & Condition(lambda: bottom_toolbar is not None)
        ),
    )


@Condition
def not_empty():
    dialog_list = get_app().layout.container.children[1].content.text.__self__
    if not dialog_list.multiple_selection:
        return True
    return bool(dialog_list.current_values)


@overload
def dialoglist(
    title: AnyFormattedText,
    values: Sequence[Tuple[_T, AnyFormattedText]],
    *,
    bottom_toolbar: str = ...,
    allow_previous: bool = ...,
    allow_next: bool = ...,
    multi_choice: Literal[False],
    show_scrollbar: bool = ...,
    exit_condition: Filter = ...,
) -> _T:
    ...


@overload
def dialoglist(
    title: AnyFormattedText,
    values: Sequence[Tuple[_T, AnyFormattedText]],
    *,
    bottom_toolbar: str = ...,
    allow_previous: bool = ...,
    allow_next: bool = ...,
    multi_choice: Literal[True],
    show_scrollbar: bool = ...,
    exit_condition: Filter = ...,
) -> List[_T]:
    ...


def dialoglist(
    title: AnyFormattedText,
    values: Sequence[Tuple[_T, AnyFormattedText]],
    *,
    bottom_toolbar: str = "",
    allow_previous: bool = True,
    allow_next: bool = False,
    multi_choice: bool,
    show_scrollbar: bool = True,
    exit_condition: Filter = Always(),
) -> Union[_T, List[_T]]:
    # Add exit key binding.
    bindings = _get_basic_keybindings(allow_previous=allow_previous, allow_next=allow_next)
    bottom_toolbar_container = _get_bottom_toolbar_container(
        ["SPACE to mark"] if multi_choice else [],
        bottom_toolbar=bottom_toolbar,
        allow_previous=allow_previous,
        allow_next=allow_next,
    )
    dialog_list = CheckboxList(values) if multi_choice else RadioList(values)
    dialog_list.show_scrollbar = show_scrollbar

    assert isinstance(dialog_list.control.key_bindings, KeyBindings)
    dialog_bindings = dialog_list.control.key_bindings
    dialog_bindings.remove("enter")

    @bindings.add("enter", filter=exit_condition)
    def exit_with_value(event: KeyPressEvent) -> None:
        if multi_choice:
            event.app.exit(result=dialog_list.current_values)
        else:
            event.app.exit(result=dialog_list.current_value)

    @bindings.add("c-c")
    def keyboard_interrupt(event: KeyPressEvent) -> None:
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    if not multi_choice:

        @dialog_bindings.add("up")
        @dialog_bindings.add("down")
        @dialog_bindings.add("pageup")
        @dialog_bindings.add("pagedown")
        @dialog_bindings.add("<any>")
        def auto_select(event: KeyPressEvent) -> None:
            key_presses = event.key_sequence
            keys = tuple(k.key for k in key_presses)
            matches = dialog_bindings.get_bindings_for_keys(keys)
            # -1 is this function while -2 should be what we want
            handler = matches[-2]
            handler.call(event)
            dialog_list._handle_enter()

    application: Application[_T] = Application(
        layout=Layout(HSplit([Label(title), dialog_list, bottom_toolbar_container])),
        key_bindings=merge_key_bindings([load_key_bindings(), bindings]),
        mouse_support=True,
        full_screen=False,
    )
    return application.run()


def prompt(
    message: AnyFormattedText = "> ",
    *,
    default: str = "",
    multiline: bool = False,
    validator: Optional[Validator] = NonEmptyValidator(),
    validate_while_typing: bool = True,
    bottom_toolbar: str = "",
    allow_previous: bool = True,
    allow_next: bool = False,
) -> str:
    bindings = _get_basic_keybindings(allow_previous=allow_previous, allow_next=allow_next)
    bottom_toolbar += _get_bottom_toolbar_text(
        ["Ctrl+ENTER for new line"] if multiline else [],
        allow_previous=allow_previous,
        allow_next=allow_next,
    )

    if multiline:

        @bindings.add("c-j", filter=emacs_insert_mode)
        def _newline(event: KeyPressEvent) -> None:
            """
            Add a new line when Ctrl+Enter is used.

            This definitely works on Windows, I don't care for more than that right now.
            """
            event.current_buffer.newline(copy_margin=not in_paste_mode())

        bindings.add("enter", filter=emacs_insert_mode & _is_returnable, eager=True)(
            get_by_name("accept-line")
        )

    return real_prompt(
        message,
        default=default,
        multiline=multiline,
        validator=validator,
        validate_while_typing=validate_while_typing,
        key_bindings=bindings,
        bottom_toolbar=bottom_toolbar,
    )
