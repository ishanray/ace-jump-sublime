import sublime, sublime_plugin
import re, itertools

last_index = 0
hints = []
search_regex = r''

next_search = False

mode = 0

def get_active_views(window):
    """Returns all currently visible views"""

    views = []
    for group in range(window.num_groups()):
        views.append(window.active_view_in_group(group))
    return views

def set_views_setting(views, setting, values):
    """Sets the values for the setting in all given views"""

    for i in range(len(views)):
        views[i].settings().set(setting, values[i])

def set_views_settings(views, settings, values):
    """Sets the values for all settings in all given views"""

    for i in range(len(settings)):
        set_views_setting(views, settings[i], values[i])

def get_views_setting(views, setting):
    """Returns the setting value for all given views"""

    settings = []
    for view in views:
        settings.append(view.settings().get(setting))
    return settings

def get_views_settings(views, settings):
    """Gets the settings for every given view"""

    values = []
    for setting in settings:
        values.append(get_views_setting(views, setting))
    return values

def set_views_syntax(views, syntax):
    """Sets the syntax highlighting for all given views"""

    for i in range(len(views)):
        views[i].set_syntax_file(syntax[i])

def set_views_sel(views, selections):
    """Sets the selections for all given views"""

    for i in range(len(views)):
        for sel in selections[i]:
            views[i].sel().add(sel)

def get_views_sel(views):
    """Returns the current selection for each from the given views"""

    selections = []
    for view in views:
        selections.append(view.sel())
    return selections

def clear_views_sel(views):
    """Clears the selection in all given views"""

    for view in views:
        view.sel().clear()

class AceJumpCommand(sublime_plugin.WindowCommand):
    """Base command class for AceJump plugin"""

    def run(self):
        self.char = ""
        self.target = ""
        self.views = []
        self.changed_views = []
        self.breakpoints = []

        self.all_views = get_active_views(self.window)
        self.syntax = get_views_setting(self.all_views, "syntax")
        self.sel = get_views_sel(self.all_views)

        settings = sublime.load_settings("AceJump.sublime-settings")
        self.highlight = settings.get("labels_scope", "invalid")
        self.labels = settings.get(
            "labels",
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        )

        self.view_settings = settings.get("view_settings", [])
        self.view_values = get_views_settings(
            self.all_views,
            self.view_settings
        )

        self.show_prompt(self.prompt(), self.init_value())

    def show_prompt(self, title, value):
        """Shows a prompt with the given title and value in the window"""

        self.window.show_input_panel(
            title, value,
            self.next_batch, self.on_input, self.submit
        )

    def next_batch(self, command):
        """Displays the next batch of labels after pressing return"""

        self.remove_labels()
        self.show_prompt(self.prompt(), self.char)

    def on_input(self, command):
        """Fires the necessary actions for the current input"""

        if len(command) == 1:
            self.char = command
            self.add_labels(self.regex().format(re.escape(self.char)))
            return

        if len(command) == 2:
            self.target = command[1]

        self.window.run_command("hide_panel", {"cancel": True})

    def submit(self):
        """Handles the behavior after closing the prompt"""

        global next_search, mode
        next_search = False

        self.remove_labels()
        set_views_sel(self.all_views, self.sel)
        set_views_syntax(self.all_views, self.syntax)
        self.jump(self.labels.find(self.target))

        mode = 0

    def add_labels(self, regex):
        """Adds labels to characters matching the regex"""

        global last_index, hints

        last_index = 0
        hints = []

        self.views = self.views_to_label()
        self.changed_views = []
        self.breakpoints = []
        changed_files = []

        for view in self.views[:]:
            if view.file_name() in changed_files:
                break

            view.run_command("add_ace_jump_labels", {
                "regex": regex,
                "labels": self.labels,
                "highlight": self.highlight
            })
            self.breakpoints.append(last_index)
            self.changed_views.append(view)
            changed_files.append(view.file_name())

            if next_search:
                break

            self.views.remove(view)

        clear_views_sel(self.all_views)

        set_views_syntax(self.all_views, list(itertools.repeat(
            "Packages/AceJump/AceJump.tmLanguage",
            len(self.all_views)
        )))

        set_views_settings(
            self.all_views,
            self.view_settings,
            self.view_values
        )

    def remove_labels(self):
        """Removes all previously added labels"""

        last_breakpoint = 0
        for breakpoint in self.breakpoints:
            if breakpoint != last_breakpoint:
                view = self.changed_views[self.view_for_index(breakpoint - 1)]
                view.run_command("remove_ace_jump_labels")
                last_breakpoint = breakpoint

    def jump(self, index):
        """Performs the jump action"""

        if self.target == "" or index < 0 or index >= last_index:
            return

        region = hints[index].begin()
        view = self.changed_views[self.view_for_index(index)]

        self.window.focus_view(view)
        view.run_command("perform_ace_jump", {"target": region})
        self.after_jump(view)

    def views_to_label(self):
        """Returns the views that still have to be labeled"""

        if mode != 0:
            return [self.window.active_view()]

        return self.all_views[:] if len(self.views) == 0 else self.views

    def view_for_index(self, index):
        """Returns a view index for the given label index"""

        for breakpoint in self.breakpoints:
            if index < breakpoint:
                return self.breakpoints.index(breakpoint)

class AceJumpWordCommand(AceJumpCommand):
    """Specialized command for word-mode"""

    def prompt(self):
        return "Head char"

    def init_value(self):
        return ""

    def regex(self):
        return r'\b{}'

    def after_jump(self, view):
        global mode

        if mode == 3:
            view.run_command("move", {"by": "word_ends", "forward": True})
            mode = 0

class AceJumpCharCommand(AceJumpCommand):
    """Specialized command for char-mode"""

    def prompt(self):
        return "Char"

    def init_value(self):
        return ""

    def regex(self):
        return r'{}'

    def after_jump(self, view):
        global mode

        if mode == 3:
            view.run_command("move", {"by": "characters", "forward": True})
            mode = 0

class AceJumpLineCommand(AceJumpCommand):
    """Specialized command for line-mode"""

    def prompt(self):
        return ""

    def init_value(self):
        return " "

    def regex(self):
        return r'(.*)[^\s](.*)\n'

    def after_jump(self, view):
        global mode

        if mode == 3:
            view.run_command("move", {"by": "lines", "forward": True})
            view.run_command("move", {"by": "characters", "forward": False})
            mode = 0

class AceJumpSelectCommand(sublime_plugin.WindowCommand):
    """Command for turning on select mode"""

    def run(self):
        global mode

        mode = 0 if mode == 1 else 1

class AceJumpAddCursorCommand(sublime_plugin.WindowCommand):
    """Command for turning on multiple cursor mode"""

    def run(self):
        global mode

        mode = 0 if mode == 2 else 2

class AceJumpAfterCommand(sublime_plugin.WindowCommand):
    """Modifier-command which lets you jump behind a character, word or line"""

    def run(self):
        global mode

        mode = 0 if mode == 3 else 3
        print(mode)

class AddAceJumpLabelsCommand(sublime_plugin.TextCommand):
    """Command for adding labels to the views"""

    def run(self, edit, regex, labels, highlight):
        global hints

        characters = self.find(regex, len(labels))
        self.add_labels(edit, characters, labels)
        self.view.add_regions("ace_jump_hints", characters, highlight)

        hints = hints + characters

    def find(self, regex, max_labels):
        """Returns a list with all occurences matching the regex"""

        global next_search, last_index

        chars = []

        visible_region = self.view.visible_region()
        next_search = next_search if next_search else visible_region.begin()
        last_search = visible_region.end()

        while (next_search < last_search and last_index < max_labels):
            word = self.view.find(regex, next_search)

            if not word:
                break

            last_index += 1
            next_search = word.end()
            chars.append(sublime.Region(word.begin(), word.begin() + 1))

        if last_index < max_labels:
            next_search = False

        return chars

    def add_labels(self, edit, regions, labels):
        """Replaces the given regions with labels"""

        for i in range(len(regions)):
            self.view.replace(
                edit, regions[i], labels[last_index + i - len(regions)]
            )

class RemoveAceJumpLabelsCommand(sublime_plugin.TextCommand):
    """Command for removing labels from the views"""

    def run(self, edit):
        self.view.erase_regions("ace_jump_hints")
        self.view.end_edit(edit)
        self.view.run_command("undo")

class PerformAceJumpCommand(sublime_plugin.TextCommand):
    """Command performing the jump"""

    def run(self, edit, target):
        if mode == 0 or mode == 3:
            self.view.sel().clear()

        self.view.sel().add(self.target_region(target))
        self.view.show(target)

    def target_region(self, target):
        if mode == 1:
            for cursor in self.view.sel():
                return sublime.Region(cursor.begin(), target)

        return sublime.Region(target)
