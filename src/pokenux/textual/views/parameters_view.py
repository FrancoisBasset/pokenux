"""Independent language preferences and versioned catalogue maintenance."""

import sys
from typing import ClassVar

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, ProgressBar, Select
from textual.worker import get_current_worker

from pokenux import __version__
from pokenux.services import user_data
from pokenux.services.assets import AssetManager, AssetManifest, AssetProgress
from pokenux.textual.utils import i18n, translator
from pokenux.textual.utils.enums import languages


class ParametersView(VerticalScroll):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "save", "Save"),
    ]
    DEFAULT_CSS = """
    ParametersView {
        height: 1fr; padding: 1 3; background: #080f19; color: #e4ebf5;
        align: center top; scrollbar-size: 1 1;
    }
    ParametersView #settings_content { width: 1fr; max-width: 108; height: auto; }
    ParametersView Label { width: 1fr; height: auto; }
    ParametersView #settings_eyebrow { color: #efc47d; text-style: bold; }
    ParametersView #settings_title { margin-top: 1; text-style: bold; color: #f2f5fc; }
    ParametersView #settings_intro { color: #99aabd; margin-bottom: 1; }
    ParametersView #language_grid {
        height: auto; grid-size: 3; grid-columns: 1fr 1fr 1fr;
        grid-rows: auto; grid-gutter: 1;
    }
    ParametersView .settings-card {
        height: auto; padding: 1 2; border: round #30435e; background: #111d2d;
    }
    ParametersView .card-title { text-style: bold; color: #83b7ff; margin-bottom: 1; }
    ParametersView .card-help { color: #a8bacf; min-height: 3; margin-bottom: 1; }
    ParametersView Select { width: 1fr; }
    ParametersView #settings_actions { height: auto; margin-top: 1; }
    ParametersView #settings_actions Button { width: 1fr; margin-right: 1; }
    ParametersView #settings_status { color: #79d7be; margin: 1 0; }
    ParametersView .warning { color: #efc47d; margin-bottom: 1; }
    ParametersView #assets_card { height: auto; margin-top: 1; }
    ParametersView #assets_title { color: #79d7be; }
    ParametersView #assets_summary { margin-bottom: 1; }
    ParametersView #assets_help { color: #99aabd; margin-bottom: 1; }
    ParametersView #asset_actions { height: auto; }
    ParametersView #asset_actions Button { width: 1fr; margin-right: 1; }
    ParametersView #assets_status { color: #a8bacf; margin-top: 1; }
    ParametersView #asset_progress { width: 1fr; margin-top: 1; }
    ParametersView #settings_version { color: #7d90aa; margin-top: 1; }
    ParametersView.narrow { padding: 1; }
    ParametersView.narrow #language_grid { grid-size: 1; grid-columns: 1fr; }
    ParametersView.narrow .card-help { min-height: 0; }
    ParametersView.narrow #asset_actions { layout: vertical; }
    ParametersView.narrow #asset_actions Button { width: 1fr; margin-right: 0; }
    """

    def __init__(self) -> None:
        super().__init__(id="parameters_view")
        self._changing = False
        self._save_state = "ready"
        self._save_error = ""
        self._asset_state = "idle"
        self._asset_error = ""
        self._asset_busy = False
        self._asset_progress: AssetProgress | None = None
        self._pending_manifest: AssetManifest | None = None
        self._asset_worker = None

    @staticmethod
    def _labels() -> dict[str, str]:
        text = i18n.text
        return {
            "settings_eyebrow": text(
                "TON ESPACE, TES PRÉFÉRENCES", "YOUR SPACE, YOUR PREFERENCES"
            ),
            "settings_title": text("Paramètres", "Settings"),
            "settings_intro": text(
                "Trois langues indépendantes. Aucun redémarrage nécessaire.",
                "Three independent language choices. No restart needed.",
            ),
            "app_title": text("01 · Interface", "01 · Interface"),
            "app_help": text(
                "Menus, boutons, consignes et notifications.",
                "Menus, buttons, instructions and notifications.",
            ),
            "pokemon_title": text("02 · Pokédex", "02 · Pokédex"),
            "pokemon_help": text(
                "Noms des Pokémon et données du Pokédex.",
                "Pokémon names and Pokédex data.",
            ),
            "tcg_title": text("03 · Cartes TCG", "03 · TCG cards"),
            "tcg_help": text(
                "Noms des cartes, séries et extensions du catalogue.",
                "Card, series and set names in the catalogue.",
            ),
            "assets_title": text("CATALOGUE & MISES À JOUR", "CATALOGUE & UPDATES"),
            "assets_help": text(
                "Les données évoluent séparément de l’application. Une mise à jour conserve ta collection et tes préférences.",
                "Game data is updated separately from the app. Updates keep your collection and preferences.",
            ),
            "settings_version": text(
                "Pokénux {version} · données locales",
                "Pokénux {version} · local data",
                version=__version__,
            ),
        }

    def compose(self) -> ComposeResult:
        labels = self._labels()
        with Vertical(id="settings_content"):
            for key in ("settings_eyebrow", "settings_title", "settings_intro"):
                yield Label(labels[key], id=key)
            yield Label("", id="config_warning", classes="warning", markup=False)
            with Grid(id="language_grid"):
                for key, selected in (
                    ("app", user_data.get_app_lang()),
                    ("pokemon", user_data.get_pokemon_lang()),
                    ("tcg", user_data.get_tcg_lang()),
                ):
                    with Vertical(classes="settings-card"):
                        yield Label(
                            labels[f"{key}_title"],
                            id=f"{key}_title",
                            classes="card-title",
                        )
                        yield Label(
                            labels[f"{key}_help"], id=f"{key}_help", classes="card-help"
                        )
                        yield Select(
                            languages,
                            id=f"{key}_lang",
                            value=selected,
                            allow_blank=False,
                        )
            with Horizontal(id="settings_actions"):
                yield Button(
                    i18n.text("Enregistrer", "Save changes"),
                    id="save_button",
                    variant="primary",
                    disabled=True,
                )
                yield Button(
                    i18n.text("Annuler les changements", "Reset changes"),
                    id="reset_button",
                )
            yield Label("", id="settings_status", markup=False)
            with Vertical(id="assets_card", classes="settings-card"):
                yield Label(
                    labels["assets_title"], id="assets_title", classes="card-title"
                )
                yield Label("", id="assets_summary", markup=False)
                yield Label(labels["assets_help"], id="assets_help")
                yield Label("", id="catalogue_warning", classes="warning", markup=False)
                with Horizontal(id="asset_actions"):
                    yield Button(
                        i18n.text("Vérifier", "Check for updates"), id="check_assets"
                    )
                    yield Button(
                        i18n.text("Installer la mise à jour", "Install update"),
                        id="update_assets",
                        disabled=True,
                    )
                    yield Button(i18n.text("Annuler", "Cancel"), id="cancel_assets")
                yield ProgressBar(total=100, show_eta=False, id="asset_progress")
                yield Label("", id="assets_status", markup=False)
            yield Label(labels["settings_version"], id="settings_version")

    def on_mount(self) -> None:
        self.refresh_language()

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 85, "narrow")

    def _dirty(self) -> bool:
        return any(
            self.query_one(f"#{key}", Select).value != getter()
            for key, getter in (
                ("app_lang", user_data.get_app_lang),
                ("pokemon_lang", user_data.get_pokemon_lang),
                ("tcg_lang", user_data.get_tcg_lang),
            )
        )

    @on(Select.Changed)
    def language_changed(self, event: Select.Changed) -> None:
        if not self.is_mounted or self._changing:
            return
        self._save_state = "dirty" if self._dirty() else "ready"
        self._refresh_save_status()
        self._refresh_assets()

    def _refresh_save_status(self) -> None:
        messages = {
            "ready": i18n.text(
                "Les préférences actuelles sont enregistrées.",
                "Your current preferences are saved.",
            ),
            "dirty": i18n.text(
                "Modifications en attente · Ctrl+S pour enregistrer.",
                "Unsaved changes · Ctrl+S to save.",
            ),
            "saved": i18n.text(
                "Préférences enregistrées. Les onglets ouverts sont à jour.",
                "Preferences saved. Open tabs are up to date.",
            ),
            "error": i18n.text(
                "Enregistrement impossible : {error}",
                "Could not save: {error}",
                error=self._save_error,
            ),
        }
        self.query_one("#settings_status", Label).update(messages[self._save_state])
        self.query_one("#save_button", Button).disabled = not self._dirty()
        warning = self.query_one("#config_warning", Label)
        warning.display = user_data.config_load_error is not None
        warning.update(
            i18n.text(
                "Le fichier de préférences est illisible. Les valeurs par défaut sont utilisées ; enregistrer remplacera ce fichier.",
                "The preferences file could not be read. Defaults are in use; saving will replace that file.",
            )
        )
        if user_data.config_load_error:
            self.query_one("#save_button", Button).disabled = False

    @on(Button.Pressed, "#save_button")
    async def action_save(self) -> None:
        try:
            user_data.save_preferences(
                app_lang=str(self.query_one("#app_lang", Select).value),
                pokemon_lang=str(self.query_one("#pokemon_lang", Select).value),
                tcg_lang=str(self.query_one("#tcg_lang", Select).value),
            )
        except (OSError, ValueError) as error:
            self._save_error = str(error)
            self._save_state = "error"
            self._refresh_save_status()
            return
        self._save_state = "saved"
        i18n.set_language(user_data.get_app_lang())
        await translator.translate_app(self.app)

    @on(Button.Pressed, "#reset_button")
    def reset_changes(self) -> None:
        self._changing = True
        try:
            for key, value in (
                ("app_lang", user_data.get_app_lang()),
                ("pokemon_lang", user_data.get_pokemon_lang()),
                ("tcg_lang", user_data.get_tcg_lang()),
            ):
                self.query_one(f"#{key}", Select).value = value
        finally:
            self._changing = False
        self._save_state = "ready"
        self._refresh_save_status()
        self._refresh_assets()

    def refresh_language(self) -> None:
        for key, label in self._labels().items():
            self.query_one(f"#{key}", Label).update(label)
        for key, pair in {
            "save_button": ("Enregistrer", "Save changes"),
            "reset_button": ("Annuler les changements", "Reset changes"),
            "check_assets": ("Vérifier", "Check for updates"),
            "update_assets": ("Installer la mise à jour", "Install update"),
            "cancel_assets": ("Annuler", "Cancel"),
        }.items():
            self.query_one(f"#{key}", Button).label = i18n.text(*pair)
        translator.refresh_bindings(self, {"save": ("Enregistrer", "Save")})
        self._refresh_save_status()
        self._refresh_assets()

    def _refresh_assets(self) -> None:
        status = AssetManager(user_data.path).status()
        label = i18n.text("Catalogue non installé", "Catalogue not installed")
        if status.installed:
            version = status.version or i18n.text("historique", "legacy")
            label = i18n.text(
                "Version : {version} · langues : {languages}",
                "Version: {version} · languages: {languages}",
                version=version,
                languages=" / ".join(lang.upper() for lang in status.languages),
            )
        self.query_one("#assets_summary", Label).update(label)
        requested = str(self.query_one("#tcg_lang", Select).value)
        missing = requested not in status.languages
        warning = self.query_one("#catalogue_warning", Label)
        warning.display = missing or status.legacy
        warning.update(
            i18n.text(
                "Catalogue historique non versionné : vérifie les mises à jour pour passer au nouveau format.",
                "Unversioned legacy catalogue: check for updates to switch to the new format.",
            )
        )
        if missing:
            available = " / ".join(lang.upper() for lang in status.languages)
            warning.update(
                i18n.text(
                    "Le catalogue {requested} manque. Les cartes utilisent {available} en attendant une mise à jour.",
                    "The {requested} catalogue is missing. Cards use {available} until an update is installed.",
                    requested=requested.upper(),
                    available=available or i18n.text("aucune donnée", "no data"),
                )
            )
        self.query_one("#check_assets", Button).disabled = self._asset_busy
        self.query_one("#update_assets", Button).disabled = (
            self._asset_busy or self._pending_manifest is None
        )
        self.query_one("#cancel_assets", Button).display = self._asset_busy
        self.query_one("#asset_progress", ProgressBar).display = self._asset_busy
        messages = {
            "idle": i18n.text(
                "La vérification se lance à ta demande.",
                "Check for updates whenever you choose.",
            ),
            "checking": i18n.text(
                "Recherche d’un catalogue plus récent…",
                "Checking for a newer catalogue…",
            ),
            "current": i18n.text(
                "Aucune mise à jour publiée n’est disponible.",
                "No published update is available.",
            ),
            "available": i18n.text(
                "Mise à jour disponible : {version}",
                "Update available: {version}",
                version=getattr(self._pending_manifest, "version", ""),
            ),
            "installed": i18n.text(
                "Catalogue mis à jour. Les données locales sont prêtes.",
                "Catalogue updated. Your local data is ready.",
            ),
            "cancelled": i18n.text(
                "Opération annulée. Les données précédentes sont conservées.",
                "Operation cancelled. Previous data has been kept.",
            ),
            "error": i18n.text(
                "Mise à jour impossible : {error}",
                "Update failed: {error}",
                error=self._asset_error,
            ),
        }
        message = messages.get(self._asset_state, "")
        if self._asset_busy and self._asset_progress is not None:
            progress = self._asset_progress
            stages = {
                "checking": ("Vérification", "Checking"),
                "downloading": ("Téléchargement", "Downloading"),
                "verifying": ("Vérification des fichiers", "Verifying files"),
                "extracting": ("Préparation du catalogue", "Preparing catalogue"),
                "activating": ("Activation", "Activating"),
            }
            message = i18n.text(
                *stages.get(progress.stage, (progress.stage, progress.stage))
            )
            percent = 100 * progress.completed / progress.total if progress.total else 0
            self.query_one("#asset_progress", ProgressBar).update(progress=percent)
        self.query_one("#assets_status", Label).update(message)

    @on(Button.Pressed, "#check_assets")
    def check_assets(self) -> None:
        self._start_assets("check")

    @on(Button.Pressed, "#update_assets")
    def update_assets(self) -> None:
        if self._pending_manifest is not None:
            self._start_assets("install")

    def _start_assets(self, action: str) -> None:
        if self._asset_busy:
            return
        self._asset_busy = True
        self._asset_progress = None
        self._asset_state = "checking"
        self._refresh_assets()
        self._asset_worker = self._run_assets(action)

    @on(Button.Pressed, "#cancel_assets")
    def cancel_assets(self) -> None:
        if self._asset_worker is not None:
            self._asset_worker.cancel()

    @work(thread=True, group="settings-assets", exclusive=True)
    def _run_assets(self, action: str) -> None:
        worker = get_current_worker()
        manager = AssetManager(user_data.path)
        try:
            if action == "check":
                manifest = manager.check_update(cancelled=lambda: worker.is_cancelled)
                state = "available" if manifest is not None else "current"
            else:
                manifest = self._pending_manifest
                if manifest is None:
                    raise ValueError(
                        i18n.text(
                            "Vérifie les mises à jour avant d’installer.",
                            "Check for updates before installing.",
                        )
                    )
                installed = manager.install(
                    manifest,
                    cancelled=lambda: worker.is_cancelled,
                    progress=self._receive_progress,
                )
                state = "installed" if installed else "cancelled"
            if worker.is_cancelled and state != "installed":
                state = "cancelled"
            if self.is_attached:
                self.app.call_from_thread(self._finish_assets, state, manifest, "")
        except Exception as error:
            if self.is_attached:
                state = "cancelled" if worker.is_cancelled else "error"
                self.app.call_from_thread(self._finish_assets, state, None, str(error))

    def _receive_progress(self, progress: AssetProgress) -> None:
        if self.is_attached:
            self.app.call_from_thread(self._show_progress, progress)

    def _show_progress(self, progress: AssetProgress) -> None:
        self._asset_progress = progress
        self._refresh_assets()

    async def _finish_assets(
        self, state: str, manifest: AssetManifest | None, error: str
    ) -> None:
        self._asset_busy = False
        self._asset_state = state
        self._asset_error = error
        if state == "available":
            self._pending_manifest = manifest
        elif state in ("current", "installed"):
            self._pending_manifest = None
        if state == "installed":
            for module_name, method in (
                ("pokenux.services.pokedex", "reload_catalogue"),
                ("pokenux.services.tcg_library", "reload_catalogues"),
            ):
                module = sys.modules.get(module_name)
                reload_catalogue = getattr(module, method, None)
                if callable(reload_catalogue):
                    reload_catalogue()
            await translator.translate_app(self.app)
        self._refresh_assets()
