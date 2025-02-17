"""
Does stuff related to the actual games.
- Adding and removing games
- Handles locating parts of a given game,
- Modifying GameInfo to support our special content folder.
- Generating and saving editoritems/vbsp_config
"""
from __future__ import annotations
from typing import Optional, Union, Any, Type, IO
from pathlib import Path
from collections.abc import Iterable, Iterator

from tkinter import *  # ui library
from tkinter import filedialog  # open/save as dialog creator
from tkinter import messagebox  # simple, standard modal dialogs

import os
import shutil
import math
import re
import io
import pickle
import pickletools
import copy
import webbrowser
from atomicwrites import atomic_write

from BEE2_config import ConfigFile
from srctools import (
    Vec, VPK, Vec_tuple,
    Property,
    VMF, Output,
    FileSystem, FileSystemChain,
)
import srctools.logger
import srctools.fgd
from app import backup, config, tk_tools, resource_gen, TK_ROOT, DEV_MODE
from localisation import gettext
import loadScreen
import packages.template_brush
import editoritems
import utils


try:
    from importlib.resources import read_binary as imp_res_read_binary
except ImportError:
    # Backport module for before Python 3.7
    from importlib_resources import read_binary as imp_res_read_binary


LOGGER = srctools.logger.get_logger(__name__)

all_games: list[Game] = []
selected_game: Optional[Game] = None
selectedGame_radio = IntVar(value=0)
game_menu: Optional[Menu] = None

# Translated text from basemodui.txt.
TRANS_DATA: dict[str, str] = {}

CONFIG = ConfigFile('games.cfg')

FILES_TO_BACKUP = [
    ('Editoritems', 'portal2_dlc2/scripts/editoritems', '.txt'),
    ('Windows VBSP', 'bin/vbsp',       '.exe'),
    ('Windows VRAD', 'bin/vrad',       '.exe'),
    ('OSX VBSP',     'bin/vbsp_osx',   ''),
    ('OSX VRAD',     'bin/vrad_osx',   ''),
    ('Linux VBSP',   'bin/vbsp_linux', ''),
    ('Linux VRAD',   'bin/vrad_linux', ''),
]

_UNLOCK_ITEMS = [
    'ITEM_EXIT_DOOR',
    'ITEM_COOP_EXIT_DOOR',
    'ITEM_ENTRY_DOOR',
    'ITEM_COOP_ENTRY_DOOR',
    'ITEM_OBSERVATION_ROOM'
    ]

# Material file used for fizzler sides.
# We use $decal because that ensures it's displayed over brushes,
# if there's base slabs or the like.
# We have to use SolidEnergy so it fades out with fizzlers.
FIZZLER_EDGE_MAT = '''\
SolidEnergy
{{
$basetexture "sprites/laserbeam"
$flowmap "effects/fizzler_flow"
$flowbounds "BEE2/fizz/fizz_side"
$flow_noise_texture "effects/fizzler_noise"
$additive 1
$translucent 1
$decal 1
$flow_color "[{}]"
$flow_vortex_color "[{}]"
'''

# Non-changing components.
FIZZLER_EDGE_MAT_PROXY = '''\
$offset "[0 0]"
Proxies
{
FizzlerVortex
{
}
MaterialModify
{
}
}
}
'''

# The location of all the instances in the game directory
INST_PATH = 'sdk_content/maps/instances/bee2'

# The line we inject to add our BEE2 folder into the game search path.
# We always add ours such that it's the highest priority, other
# than '|gameinfo_path|.'
GAMEINFO_LINE = 'Game\t"BEE2"'

# We inject this line to recognise where our sounds start, so we can modify
# them.
EDITOR_SOUND_LINE = '// BEE2 SOUNDS BELOW'

# The progress bars used when exporting data into a game
export_screen = loadScreen.LoadScreen(
    ('BACK', 'Backup Original Files'),
    (backup.AUTO_BACKUP_STAGE, 'Backup Puzzles'),
    ('EXP', 'Export Configuration'),
    ('COMP', 'Copy Compiler'),
    ('RES', 'Copy Resources'),
    ('MUS', 'Copy Music'),
    title_text='Exporting',
)

EXE_SUFFIX = (
    '.exe' if utils.WIN else
    '_osx' if utils.MAC else
    '_linux' if utils.LINUX else
    ''
)

# The systems we need to copy to ingame resources
res_system = FileSystemChain()

# We search for Tag and Mel's music files, and copy them to games on export.
# That way they can use the files.
MUSIC_MEL_VPK: Optional[VPK] = None
MUSIC_TAG_LOC: Optional[str] = None
TAG_COOP_INST_VMF: Optional[VMF] = None

# The folder with the file...
MUSIC_MEL_DIR = 'Portal Stories Mel/portal_stories/pak01_dir.vpk'
MUSIC_TAG_DIR = 'aperture tag/aperturetag/sound/music'

# Location of coop instance for Tag gun
TAG_GUN_COOP_INST = ('aperture tag/sdk_content/maps/'
                     'instances/alatag/lp_paintgun_instance_coop.vmf')

# All the PS:Mel track names - all the resources are in the VPK,
# this allows us to skip looking through all the other files..
MEL_MUSIC_NAMES = """\
portal2_background01.wav
sp_a1_garden.wav
sp_a1_lift.wav
sp_a1_mel_intro.wav
sp_a1_tramride.wav
sp_a2_dont_meet_virgil.wav
sp_a2_firestorm_exploration.wav
sp_a2_firestorm_explosion.wav
sp_a2_firestorm_openvault.wav
sp_a2_garden_destroyed_01.wav
sp_a2_garden_destroyed_02.wav
sp_a2_garden_destroyed_portalgun.wav
sp_a2_garden_destroyed_vault.wav
sp_a2_once_upon.wav
sp_a2_past_power_01.wav
sp_a2_past_power_02.wav
sp_a2_underbounce.wav
sp_a3_concepts.wav
sp_a3_concepts_funnel.wav
sp_a3_faith_plate.wav
sp_a3_faith_plate_funnel.wav
sp_a3_junkyard.wav
sp_a3_junkyard_offices.wav
sp_a3_paint_fling.wav
sp_a3_paint_fling_funnel.wav
sp_a3_transition.wav
sp_a3_transition_funnel.wav
sp_a4_destroyed.wav
sp_a4_destroyed_funnel.wav
sp_a4_factory.wav
sp_a4_factory_radio.wav
sp_a4_overgrown.wav
sp_a4_overgrown_funnel.wav
sp_a4_tb_over_goo.wav
sp_a4_tb_over_goo_funnel.wav
sp_a4_two_of_a_kind.wav
sp_a4_two_of_a_kind_funnel.wav
sp_a5_finale01_01.wav
sp_a5_finale01_02.wav
sp_a5_finale01_03.wav
sp_a5_finale01_funnel.wav
sp_a5_finale02_aegis_revealed.wav
sp_a5_finale02_lastserver.wav
sp_a5_finale02_room01.wav
sp_a5_finale02_room02.wav
sp_a5_finale02_room02_serious.wav
sp_a5_finale02_stage_00.wav
sp_a5_finale02_stage_01.wav
sp_a5_finale02_stage_02.wav
sp_a5_finale02_stage_end.wav\
""".split()
# Not used...
# sp_a1_garden_jukebox01.wav
# sp_a1_jazz.wav
# sp_a1_jazz_enterstation.wav
# sp_a1_jazz_tramride.wav
# still_alive_gutair_cover.wav
# want_you_gone_guitar_cover.wav

# HammerAddons tags relevant to P2.
FGD_TAGS = frozenset({
    'SINCE_HL2', 'SINCE_HLS', 'SINCE_EP1', 'SINCE_EP2', 'SINCE_TF2',
    'SINCE_P1', 'SINCE_L4D', 'SINCE_L4D2', 'SINCE_ASW', 'SINCE_P2',
    'P2', 'UNTIL_CSGO', 'VSCRIPT', 'INST_IO'
})


def load_filesystems(package_sys: Iterable[FileSystem]) -> None:
    """Load package filesystems into a chain."""
    for system in package_sys:
        res_system.add_sys(system, prefix='resources/')


def translate(string: str) -> str:
    """Translate the string using Portal 2's language files.

    This is needed for Valve items, since they translate automatically.
    """
    return TRANS_DATA.get(string, string)


def setgame_callback(selected_game):
    """Callback function run when games are selected."""
    pass


def quit_application():
    """Command run to quit the application.

    This is overwritten by UI later.
    """
    import sys
    sys.exit()


def should_backup_app(file: str) -> bool:
    """Check if the given application is Valve's, or ours.

    We do this by checking for the PyInstaller archive.
    """
    # We can't import PyInstaller properly while frozen, so copy over
    # the important code.

    # from PyInstaller.archive.readers import CArchiveReader
    try:
        f = open(file, 'rb')
    except FileNotFoundError:
        # We don't want to backup missing files.
        return False

    SIZE = 4096

    with f:
        f.seek(0, io.SEEK_END)
        if f.tell() < SIZE:
            return False  # Too small.

        # Read out the last 4096 bytes, and look for the sig in there.
        f.seek(-SIZE, io.SEEK_END)
        end_data = f.read(SIZE)
        # We also look for BenVlodgi, to catch the BEE 1.06 precompiler.
        return b'BenVlodgi' not in end_data and b'MEI\014\013\012\013\016' not in end_data


class Game:
    def __init__(
        self,
        name: str,
        steam_id: str,
        folder: str,
        mod_times: dict[str, int],
    ) -> None:
        self.name = name
        self.steamID = steam_id
        self.root = folder
        # The last modified date of packages, so we know whether to copy it over.
        self.mod_times = mod_times

    @classmethod
    def parse(cls, gm_id: str, config: ConfigFile) -> 'Game':
        """Parse out the given game ID from the config file."""
        steam_id = config.get_val(gm_id, 'SteamID', '<none>')
        if not steam_id.isdigit():
            raise ValueError(f'Game {gm_id} has invalid Steam ID: {steam_id}')

        folder = config.get_val(gm_id, 'Dir', '')
        if not folder:
            raise ValueError(f'Game {gm_id} has no folder!')

        if not os.path.exists(folder):
            raise ValueError(f'Folder {folder} does not exist for game {gm_id}!')

        mod_times = {}

        for name, value in config.items(gm_id):
            if name.startswith('pack_mod_'):
                mod_times[name[9:].casefold()] = srctools.conv_int(value)

        return cls(gm_id, steam_id, folder, mod_times)

    def save(self) -> None:
        """Write a game into the config page."""
        # Wipe the original configs
        CONFIG[self.name] = {}
        CONFIG[self.name]['SteamID'] = self.steamID
        CONFIG[self.name]['Dir'] = self.root
        for pack, mod_time in self.mod_times.items():
            CONFIG[self.name]['pack_mod_' + pack] = str(mod_time)

    def dlc_priority(self) -> Iterator[str]:
        """Iterate through all subfolders, in order of high to low priority.

        We assume the priority follows:
        1. update,
        2. portal2_dlc99, ..., portal2_dlc2, portal2_dlc1
        3. portal2,
        4. <all others>
        """
        dlc_count = 1
        priority = ["portal2"]
        while os.path.isdir(self.abs_path("portal2_dlc" + str(dlc_count))):
            priority.append("portal2_dlc" + str(dlc_count))
            dlc_count += 1
        if os.path.isdir(self.abs_path("update")):
            priority.append("update")
        # files are definitely not here
        blacklist = ("bin", "Soundtrack", "sdk_tools", "sdk_content")
        yield from reversed(priority)
        for folder in os.listdir(self.root):
            if (os.path.isdir(self.abs_path(folder)) and
                    folder not in priority and
                    folder not in blacklist):
                yield folder

    def abs_path(self, path: Union[str, Path]) -> str:
        """Return the full path to something relative to this game's folder."""
        return os.path.normcase(os.path.join(self.root, path))

    def add_editor_sounds(
        self,
        sounds: Iterable[packages.EditorSound],
    ) -> None:
        """Add soundscript items so they can be used in the editor."""
        # PeTI only loads game_sounds_editor, so we must modify that.
        # First find the highest-priority file
        for folder in self.dlc_priority():
            file = self.abs_path(os.path.join(
                folder,
                'scripts',
                'game_sounds_editor.txt'
            ))
            if os.path.isfile(file):
                break  # We found it
        else:
            # Assume it's in dlc2
            file = self.abs_path(os.path.join(
                'portal2_dlc2',
                'scripts',
                'game_sounds_editor.txt',
            ))
        try:
            with open(file, encoding='utf8') as f1:
                file_data = list(f1)
        except FileNotFoundError:
            # If the file doesn't exist, we'll just write our stuff in.
            file_data = []
        for i, line in enumerate(file_data):
            if line.strip() == EDITOR_SOUND_LINE:
                # Delete our marker line and everything after it
                del file_data[i:]
                break

        # Then add our stuff!
        with atomic_write(file, overwrite=True, encoding='utf8') as f:
            f.writelines(file_data)
            f.write(EDITOR_SOUND_LINE + '\n')
            for sound in sounds:
                for line in sound.data.export():
                    f.write(line)
                f.write('\n')  # Add a little spacing

    def edit_gameinfo(self, add_line=False) -> None:
        """Modify all gameinfo.txt files to add or remove our line.

        Add_line determines if we are adding or removing it.
        """

        for folder in self.dlc_priority():
            info_path = os.path.join(self.root, folder, 'gameinfo.txt')
            if os.path.isfile(info_path):
                with open(info_path, encoding='utf8') as file:
                    data = list(file)

                for line_num, line in reversed(list(enumerate(data))):
                    clean_line = srctools.clean_line(line)
                    if add_line:
                        if clean_line == GAMEINFO_LINE:
                            break  # Already added!
                        elif '|gameinfo_path|' in clean_line:
                            LOGGER.debug(
                                "Adding gameinfo hook to {}",
                                info_path,
                            )
                            # Match the line's indentation
                            data.insert(
                                line_num+1,
                                utils.get_indent(line) + GAMEINFO_LINE + '\n',
                                )
                            break
                    else:
                        if clean_line == GAMEINFO_LINE:
                            LOGGER.debug(
                                "Removing gameinfo hook from {}", info_path
                            )
                            data.pop(line_num)
                            break
                else:
                    if add_line:
                        LOGGER.warning(
                            'Failed editing "{}" to add our special folder!',
                            info_path,
                        )
                    continue

                with atomic_write(info_path, overwrite=True, encoding='utf8') as file2:
                    for line in data:
                        file2.write(line)
        if not add_line:
            # Restore the original files!

            for name, filename, ext in FILES_TO_BACKUP:
                item_path = self.abs_path(f"{filename}{ext}")
                backup_path = self.abs_path(f'{filename}_original{ext}')
                old_version = self.abs_path(f'{filename}_styles{ext}')
                if os.path.isfile(old_version):
                    LOGGER.info('Restoring Stylechanger version of "{}"!', name)
                    shutil.copy(old_version, item_path)
                elif os.path.isfile(backup_path):
                    LOGGER.info('Restoring original "{}"!', name)
                    shutil.move(backup_path, item_path)
            self.clear_cache()

    def edit_fgd(self, add_lines: bool=False) -> None:
        """Add our FGD files to the game folder.

        This is necessary so that VBSP offsets the entities properly,
        if they're in instances.
        Add_line determines if we are adding or removing it.
        """
        file: IO[bytes]
        # We do this in binary to ensure non-ASCII characters pass though
        # untouched.

        fgd_path = self.abs_path('bin/portal2.fgd')
        try:
            with open(fgd_path, 'rb') as file:
                data = file.readlines()
        except FileNotFoundError:
            LOGGER.warning('No FGD file? ("{}")', fgd_path)
            return

        for i, line in enumerate(data):
            match = re.match(
                br'// BEE\W*2 EDIT FLAG\W*=\W*([01])',
                line,
                re.IGNORECASE,
            )
            if match:
                if match.group(1) == b'0':
                    LOGGER.info('FGD editing disabled by file.')
                    return  # User specifically disabled us.
                # Delete all data after this line.
                del data[i:]
                break

        engine_fgd = srctools.FGD.engine_dbase()
        engine_fgd.collapse_bases()
        fgd = srctools.FGD()

        for ent in engine_fgd:
            if ent.classname.startswith('comp_') or ent.classname == "hammer_notes":
                fgd.entities[ent.classname] = ent
                ent.strip_tags(FGD_TAGS)

        with atomic_write(fgd_path, overwrite=True, mode='wb') as file:
            for line in data:
                file.write(line)
            if add_lines:
                file.write(
                    b'// BEE 2 EDIT FLAG = 1 \n'
                    b'// Added automatically by BEE2. Set above to "0" to '
                    b'allow editing below text without being overwritten.\n'
                    b'\n\n'
                )
                with utils.install_path('BEE2.fgd').open('rb') as bee2_fgd:
                    shutil.copyfileobj(bee2_fgd, file)
                file_str = io.TextIOWrapper(file, encoding='iso-8859-1')
                fgd.export(file_str)
                file_str.detach()  # Ensure it doesn't close it itself.

    def cache_invalid(self) -> bool:
        """Check to see if the cache is valid."""
        if config.get_cur_conf(config.GenOptions).preserve_resources:
            # Skipped always
            return False

        # Check lengths, to ensure we re-extract if packages were removed.
        if len(packages.LOADED.packages) != len(self.mod_times):
            LOGGER.info('Need to extract - package counts inconsistent!')
            return True

        return any(
            pack.is_stale(self.mod_times.get(pack_id.casefold(), 0))
            for pack_id, pack in
            packages.LOADED.packages.items()
        )

    def refresh_cache(self, already_copied: set[str]) -> None:
        """Copy over the resource files into this game.

        already_copied is passed from copy_mod_music(), to
        indicate which files should remain. It is the full path to the files.
        """
        screen_func = export_screen.step

        with res_system:
            for file in res_system.walk_folder_repeat():
                try:
                    start_folder, path = file.path.split('/', 1)
                except ValueError:
                    LOGGER.warning('File in resources root: "{}"!', file.path)
                    continue

                start_folder = start_folder.casefold()

                if start_folder == 'instances':
                    dest = self.abs_path(INST_PATH + '/' + path)
                elif start_folder in ('bee2', 'music_samp'):
                    screen_func('RES', start_folder)
                    continue  # Skip app icons and music samples.
                else:
                    # Preserve original casing.
                    dest = self.abs_path(os.path.join('bee2', file.path))

                # Already copied from another package.
                if dest in already_copied:
                    screen_func('RES', dest)
                    continue
                already_copied.add(dest)

                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with file.open_bin() as fsrc, open(dest, 'wb') as fdest:
                    shutil.copyfileobj(fsrc, fdest)
                screen_func('RES', file.path)

        LOGGER.info('Cache copied.')

        for path in [INST_PATH, 'bee2']:
            abs_path = self.abs_path(path)
            for dirpath, dirnames, filenames in os.walk(abs_path):
                for filename in filenames:
                    # Keep VMX backups, disabled editor models, and the coop
                    # gun instance.
                    if filename.endswith(('.vmx', '.mdl_dis', 'tag_coop_gun.vmf')):
                        continue
                    path = os.path.join(dirpath, filename)

                    if path.casefold() not in already_copied:
                        LOGGER.info('Deleting: {}', path)
                        os.remove(path)

        # Save the new cache modification date.
        self.mod_times.clear()
        for pack_id, pack in packages.LOADED.packages.items():
            self.mod_times[pack_id.casefold()] = pack.get_modtime()
        self.save()
        CONFIG.save_check()

    def clear_cache(self) -> None:
        """Remove all resources from the game."""
        shutil.rmtree(self.abs_path(INST_PATH), ignore_errors=True)
        shutil.rmtree(self.abs_path('bee2/'), ignore_errors=True)
        shutil.rmtree(self.abs_path('bin/bee2/'), ignore_errors=True)

        try:
            packages.StyleVPK.clear_vpk_files(self)
        except PermissionError:
            pass

        self.mod_times.clear()

    def export(
        self,
        style: packages.Style,
        selected_objects: dict[Type[packages.PakObject], Any],
        should_refresh=False,
    ) -> tuple[bool, bool]:
        """Generate the editoritems.txt and vbsp_config.

        - If no backup is present, the original editoritems is backed up.
        - For each object type, run its .export() function with the given
        - item.
        - Styles are a special case.
        """

        LOGGER.info('-' * 20)
        LOGGER.info('Exporting Items and Style for "{}"!', self.name)

        LOGGER.info('Style = {}', style.id)
        for obj_type, selected in selected_objects.items():
            # Skip the massive dict in items
            if obj_type is packages.Item:
                selected = selected[0]
            LOGGER.info('{} = {}', obj_type, selected)

        # VBSP, VRAD, editoritems
        export_screen.set_length('BACK', len(FILES_TO_BACKUP))
        # files in compiler/
        try:
            num_compiler_files = sum(1 for file in utils.install_path('compiler').rglob('*'))
        except FileNotFoundError:
            num_compiler_files = 0

        if self.steamID == utils.STEAM_IDS['APERTURE TAG']:
            # Coop paint gun instance
            num_compiler_files += 1

        if num_compiler_files == 0:
            LOGGER.warning('No compiler files!')
            export_screen.skip_stage('COMP')
        else:
            export_screen.set_length('COMP', num_compiler_files)

        LOGGER.info('Should refresh: {}', should_refresh)
        if should_refresh:
            # Check to ensure the cache needs to be copied over..
            should_refresh = self.cache_invalid()
            if should_refresh:
                LOGGER.info("Cache invalid - copying..")
            else:
                LOGGER.info("Skipped copying cache!")

        # Each object type
        # Editoritems
        # VBSP_config
        # Instance list
        # Editor models
        # Template file
        # FGD file
        # Gameinfo
        # Misc resources
        export_screen.set_length('EXP', len(packages.OBJ_TYPES) + 8)

        # Do this before setting music and resources,
        # those can take time to compute.
        export_screen.show()
        try:

            if should_refresh:
                # Count the files.
                export_screen.set_length(
                    'RES',
                    sum(1 for _ in res_system.walk_folder_repeat()),
                )
            else:
                export_screen.skip_stage('RES')
                export_screen.skip_stage('MUS')

            # Make the folders we need to copy files to, if desired.
            os.makedirs(self.abs_path('bin/bee2/'), exist_ok=True)

            # Start off with the style's data.
            vbsp_config = Property.root()
            vbsp_config += style.config().copy()

            all_items = style.items.copy()
            renderables = style.renderables.copy()
            resources: dict[str, bytes] = {}

            export_screen.step('EXP', 'style-conf')

            vpk_success = True

            # Export each object type.
            for obj_type in packages.OBJ_TYPES.values():
                if obj_type is packages.Style:
                    continue  # Done above already

                LOGGER.info('Exporting "{}"', obj_type.__name__)

                try:
                    obj_type.export(packages.ExportData(
                        game=self,
                        selected=selected_objects.get(obj_type, None),
                        all_items=all_items,
                        renderables=renderables,
                        vbsp_conf=vbsp_config,
                        packset=packages.LOADED,  # TODO
                        selected_style=style,
                        resources=resources,
                    ))
                except packages.NoVPKExport:
                    # Raised by StyleVPK to indicate it failed to copy.
                    vpk_success = False

                export_screen.step('EXP', obj_type.__name__)

            packages.template_brush.write_templates(self)
            export_screen.step('EXP', 'template_brush')

            vbsp_config.set_key(('Options', 'Game_ID'), self.steamID)
            vbsp_config.set_key(('Options', 'dev_mode'), srctools.bool_as_int(DEV_MODE.get()))

            # If there are multiple of these blocks, merge them together.
            # They will end up in this order.
            vbsp_config.merge_children(
                'Textures',
                'Fizzlers',
                'Options',
                'StyleVars',
                'DropperItems',
                'Conditions',
                'Quotes',
                'PackTriggers',
            )

            for name, file, ext in FILES_TO_BACKUP:
                item_path = self.abs_path(file + ext)
                backup_path = self.abs_path(file + '_original' + ext)

                if not os.path.isfile(item_path):
                    # We can't backup at all.
                    should_backup = False
                elif name == 'Editoritems':
                    should_backup = not os.path.isfile(backup_path)
                else:
                    # Always backup the non-_original file, it'd be newer.
                    # But only if it's Valves - not our own.
                    should_backup = should_backup_app(item_path)
                    backup_is_good = should_backup_app(backup_path)
                    LOGGER.info(
                        '{}{}: normal={}, backup={}',
                        file, ext,
                        'Valve' if should_backup else 'BEE2',
                        'Valve' if backup_is_good else 'BEE2',
                    )

                    if not should_backup and not backup_is_good:
                        # It's a BEE2 application, we have a problem.
                        # Both the real and backup are bad, we need to get a
                        # new one.
                        try:
                            os.remove(backup_path)
                        except FileNotFoundError:
                            pass
                        try:
                            os.remove(item_path)
                        except FileNotFoundError:
                            pass

                        export_screen.reset()
                        if messagebox.askokcancel(
                            title=gettext('BEE2 - Export Failed!'),
                            message=gettext(
                                'Compiler file {file} missing. '
                                'Exit Steam applications, then press OK '
                                'to verify your game cache. You can then '
                                'export again.'
                            ).format(
                                file=file + ext,
                            ),
                            master=TK_ROOT,
                        ):
                            webbrowser.open('steam://validate/' + str(self.steamID))
                        return False, vpk_success

                if should_backup:
                    LOGGER.info('Backing up original {}!', name)
                    shutil.copy(item_path, backup_path)
                export_screen.step('BACK', name)

            # Backup puzzles, if desired
            backup.auto_backup(selected_game, export_screen)

            # Special-case: implement the UnlockDefault stlylevar here,
            # so all items are modified.
            if selected_objects[packages.StyleVar]['UnlockDefault']:
                LOGGER.info('Unlocking Items!')
                for i, item in enumerate(all_items):
                    # If the Unlock Default Items stylevar is enabled, we
                    # want to force the corridors and obs room to be
                    # deletable and copyable
                    # Also add DESIRES_UP, so they place in the correct orientation
                    if item.id in _UNLOCK_ITEMS:
                        all_items[i] = item = copy.copy(item)
                        item.deletable = item.copiable = True
                        item.facing = editoritems.DesiredFacing.UP

            LOGGER.info('Editing Gameinfo...')
            self.edit_gameinfo(True)
            export_screen.step('EXP', 'gameinfo')

            if not config.get_cur_conf(config.GenOptions).preserve_resources:
                LOGGER.info('Adding ents to FGD.')
                self.edit_fgd(True)
            export_screen.step('EXP', 'fgd')

            # atomicwrites writes to a temporary file, then renames in one step.
            # This ensures editoritems won't be half-written.
            LOGGER.info('Writing Editoritems script...')
            with atomic_write(self.abs_path('portal2_dlc2/scripts/editoritems.txt'), overwrite=True, encoding='utf8') as editor_file:
                editoritems.Item.export(editor_file, all_items, renderables, id_filenames=False)
            export_screen.step('EXP', 'editoritems')

            LOGGER.info('Writing Editoritems database...')
            with open(self.abs_path('bin/bee2/editor.bin'), 'wb') as inst_file:
                pick = pickletools.optimize(pickle.dumps(all_items))
                inst_file.write(pick)
            export_screen.step('EXP', 'editoritems_db')

            LOGGER.info('Writing VBSP Config!')
            os.makedirs(self.abs_path('bin/bee2/'), exist_ok=True)
            with open(self.abs_path('bin/bee2/vbsp_config.cfg'), 'w', encoding='utf8') as vbsp_file:
                for line in vbsp_config.export():
                    vbsp_file.write(line)
            export_screen.step('EXP', 'vbsp_config')

            if num_compiler_files > 0:
                LOGGER.info('Copying Custom Compiler!')
                compiler_src = utils.install_path('compiler')
                for comp_file in compiler_src.rglob('*'):
                    # Ignore folders.
                    if comp_file.is_dir():
                        continue

                    dest = self.abs_path('bin' / comp_file.relative_to(compiler_src))

                    LOGGER.info('\t* {} -> {}', comp_file, dest)

                    folder = Path(dest).parent
                    if not folder.exists():
                        folder.mkdir(parents=True, exist_ok=True)

                    try:
                        if os.path.isfile(dest):
                            # First try and give ourselves write-permission,
                            # if it's set read-only.
                            utils.unset_readonly(dest)
                        shutil.copy(comp_file, dest)
                    except PermissionError:
                        # We might not have permissions, if the compiler is currently
                        # running.
                        export_screen.reset()
                        messagebox.showerror(
                            title=gettext('BEE2 - Export Failed!'),
                            message=gettext('Copying compiler file {file} failed. '
                                      'Ensure {game} is not running.').format(
                                        file=comp_file,
                                        game=self.name,
                                    ),
                            master=TK_ROOT,
                        )
                        return False, vpk_success
                    export_screen.step('COMP', str(comp_file))

            if should_refresh:
                LOGGER.info('Copying Resources!')
                music_files = self.copy_mod_music()
                self.refresh_cache(music_files)

            LOGGER.info('Optimizing editor models...')
            self.clean_editor_models(all_items)
            export_screen.step('EXP', 'editor_models')

            LOGGER.info('Writing fizzler sides...')
            self.generate_fizzler_sides(vbsp_config)
            resource_gen.make_cube_colourizer_legend(Path(self.abs_path('bee2')))
            export_screen.step('EXP', 'fizzler_sides')

            # Write generated resources, after the regular ones have been copied.
            for filename, data in resources.items():
                LOGGER.info('Writing {}...', filename)
                loc = Path(self.abs_path(filename))
                loc.parent.mkdir(parents=True, exist_ok=True)
                with loc.open('wb') as f1:
                    f1.write(data)

            if self.steamID == utils.STEAM_IDS['APERTURE TAG']:
                os.makedirs(self.abs_path('sdk_content/maps/instances/bee2/'), exist_ok=True)
                with open(self.abs_path('sdk_content/maps/instances/bee2/tag_coop_gun.vmf'), 'w') as f2:
                    TAG_COOP_INST_VMF.export(f2)

            export_screen.reset()  # Hide loading screen, we're done
            return True, vpk_success
        except loadScreen.Cancelled:
            return False, False

    def clean_editor_models(self, items: Iterable[editoritems.Item]) -> None:
        """The game is limited to having 1024 models loaded at once.

        Editor models are always being loaded, so we need to keep the number
        small. Go through editoritems, and disable (by renaming to .mdl_dis)
        unused ones.
        """
        # If set, force them all to be present.
        force_on = config.get_cur_conf(config.GenOptions).force_all_editor_models

        used_models = {
            str(mdl.with_suffix('')).casefold()
            for item in items
            for subtype in item.subtypes
            for mdl in subtype.models
        }

        mdl_count = 0

        for mdl_folder in [
            self.abs_path('bee2/models/props_map_editor/'),
            self.abs_path('bee2_dev/models/props_map_editor/'),
        ]:
            if not os.path.exists(mdl_folder):
                continue
            for file in os.listdir(mdl_folder):
                if not file.endswith(('.mdl', '.mdl_dis')):
                    continue

                mdl_count += 1

                file_no_ext, ext = os.path.splitext(file)
                if force_on or file_no_ext.casefold() in used_models:
                    new_ext = '.mdl'
                else:
                    new_ext = '.mdl_dis'

                if new_ext != ext:
                    try:
                        os.remove(os.path.join(mdl_folder, file_no_ext + new_ext))
                    except FileNotFoundError:
                        pass
                    os.rename(
                        os.path.join(mdl_folder, file_no_ext + ext),
                        os.path.join(mdl_folder, file_no_ext + new_ext),
                    )

        if mdl_count != 0:
            LOGGER.info(
                '{}/{} ({:.0%}) editor models used.',
                len(used_models),
                mdl_count,
                len(used_models) / mdl_count,
            )
        else:
            LOGGER.warning('No custom editor models!')

    def generate_fizzler_sides(self, conf: Property):
        """Create the VMTs used for fizzler sides."""
        fizz_colors: dict[Vec_tuple, tuple[float, str]] = {}
        mat_path = self.abs_path('bee2/materials/bee2/fizz_sides/side_color_')
        for brush_conf in conf.find_all('Fizzlers', 'Fizzler', 'Brush'):
            fizz_color = brush_conf['Side_color', '']
            if fizz_color:
                fizz_colors[Vec.from_str(fizz_color).as_tuple()] = (
                    brush_conf.float('side_alpha', 1),
                    brush_conf['side_vortex', fizz_color]
                )
        if fizz_colors:
            os.makedirs(self.abs_path('bee2/materials/bee2/fizz_sides/'), exist_ok=True)
        for fizz_color_vec, (alpha, fizz_vortex_color) in fizz_colors.items():
            file_path = mat_path + '{:02X}{:02X}{:02X}.vmt'.format(
                round(fizz_color_vec.x * 255),
                round(fizz_color_vec.y * 255),
                round(fizz_color_vec.z * 255),
            )
            with open(file_path, 'w') as f:
                f.write(FIZZLER_EDGE_MAT.format(Vec(fizz_color_vec), fizz_vortex_color))
                if alpha != 1:
                    # Add the alpha value, but replace 0.5 -> .5 to save a char.
                    f.write('$outputintensity {}\n'.format(format(alpha, 'g').replace('0.', '.')))
                f.write(FIZZLER_EDGE_MAT_PROXY)

    def launch(self):
        """Try and launch the game."""
        webbrowser.open('steam://rungameid/' + str(self.steamID))

    def copy_mod_music(self) -> set[str]:
        """Copy music files from Tag and PS:Mel.

        This returns a list of all the paths it copied to.
        """
        tag_dest = self.abs_path('bee2/sound/music/')
        # Mel's music has similar names to P2's, so put it in a subdir
        # to avoid confusion.
        mel_dest = self.abs_path('bee2/sound/music/mel/')
        # Obviously Tag has its music already...
        copy_tag = (
            self.steamID != utils.STEAM_IDS['APERTURE TAG'] and
            MUSIC_TAG_LOC is not None
        )

        copied_files = set()

        file_count = 0
        if copy_tag:
            file_count += len(os.listdir(MUSIC_TAG_LOC))
        if MUSIC_MEL_VPK is not None:
            file_count += len(MEL_MUSIC_NAMES)

        export_screen.set_length('MUS', file_count)

        # We know that it's very unlikely Tag or Mel's going to update
        # the music files. So we can check to see if they already exist,
        # and if so skip copying - that'll speed up any exports after the
        # first.
        # We'll still go through the list though, just in case one was
        # deleted.

        if copy_tag:
            os.makedirs(tag_dest, exist_ok=True)
            for filename in os.listdir(MUSIC_TAG_LOC):
                src_loc = os.path.join(MUSIC_TAG_LOC, filename)
                dest_loc = os.path.join(tag_dest, filename)
                if os.path.isfile(src_loc) and not os.path.exists(dest_loc):
                    shutil.copy(src_loc, dest_loc)
                copied_files.add(dest_loc)
                export_screen.step('MUS')

        if MUSIC_MEL_VPK is not None:
            os.makedirs(mel_dest, exist_ok=True)
            for filename in MEL_MUSIC_NAMES:
                dest_loc = os.path.join(mel_dest, filename)
                if not os.path.exists(dest_loc):
                    with open(dest_loc, 'wb') as dest:
                        dest.write(MUSIC_MEL_VPK['sound/music', filename].read())
                copied_files.add(dest_loc)
                export_screen.step('MUS')

        return copied_files

    def init_trans(self):
        """Try and load a copy of basemodui from Portal 2 to translate.

        Valve's items use special translation strings which would look ugly
        if we didn't convert them.
        """
        # Already loaded
        if TRANS_DATA:
            return

        # Allow overriding.
        try:
            lang = os.environ['BEE2_P2_LANG']
        except KeyError:
            pass
        else:
            self.load_trans(lang)
            return

        # We need to first figure out what language is used (if not English),
        # then load in the file. This is saved in the 'appmanifest',

        try:
            appman_file = open(self.abs_path('../../appmanifest_620.acf'))
        except FileNotFoundError:
            # Portal 2 isn't here...
            return

        with appman_file:
            appman = Property.parse(appman_file, 'appmanifest_620.acf')
        try:
            lang = appman.find_key('AppState').find_key('UserConfig')['language']
        except LookupError:
            return

        self.load_trans(lang)

    def load_trans(self, lang) -> None:
        """Actually load the translation."""
        # Already loaded
        if TRANS_DATA:
            return

        basemod_loc = self.abs_path(
            '../Portal 2/portal2_dlc2/resource/basemodui_' + lang + '.txt'
        )

        # Basemod files are encoded in UTF-16.
        try:
            basemod_file = open(basemod_loc, encoding='utf16')
        except FileNotFoundError:
            return
        with basemod_file:
            # This file is in keyvalues format, supposedly.
            # But it's got a bunch of syntax errors - extra quotes,
            # missing brackets.
            # The structure doesn't matter, so just process line by line.
            for line in basemod_file:
                try:
                    __, key, __, value, __ = line.split('"')
                except ValueError:
                    continue
                # Ignore non-puzzlemaker keys.
                if key.startswith('PORTAL2_PuzzleEditor'):
                    TRANS_DATA[key] = value.replace("\\'", "'")

        if gettext('Quit') == '####':
            # Dummy translations installed, apply here too.
            for key in TRANS_DATA:
                TRANS_DATA[key] = gettext(key)


def find_steam_info(game_dir):
    """Determine the steam ID and game name of this folder, if it has one.

    This only works on Source games!
    """
    game_id = None
    name = None
    found_name = False
    found_id = False
    for folder in os.listdir(game_dir):
        info_path = os.path.join(game_dir, folder, 'gameinfo.txt')
        if os.path.isfile(info_path):
            with open(info_path) as file:
                for line in file:
                    clean_line = srctools.clean_line(line).replace('\t', ' ')
                    if not found_id and 'steamappid' in clean_line.casefold():
                        raw_id = clean_line.casefold().replace(
                            'steamappid', '').strip()
                        if raw_id.isdigit():
                            game_id = raw_id
                    elif not found_name and 'game ' in clean_line.casefold():
                        found_name = True
                        ind = clean_line.casefold().rfind('game') + 4
                        name = clean_line[ind:].strip().strip('"')
                    if found_name and found_id:
                        break
        if found_name and found_id:
            break
    return game_id, name


def scan_music_locs():
    """Try and determine the location of Aperture Tag and PS:Mel.

    If successful we can export the music to games.
    """
    global MUSIC_TAG_LOC, MUSIC_MEL_VPK
    found_tag = False
    steamapp_locs = set()
    for gm in all_games:
        steamapp_locs.add(os.path.normpath(gm.abs_path('../')))

    for loc in steamapp_locs:
        tag_loc = os.path.join(loc, MUSIC_TAG_DIR)
        mel_loc = os.path.join(loc, MUSIC_MEL_DIR)
        if os.path.exists(tag_loc) and not found_tag:
            found_tag = True
            try:
                make_tag_coop_inst(loc)
            except FileNotFoundError:
                messagebox.showinfo(
                    message=gettext('Ap-Tag Coop gun instance not found!\n'
                              'Coop guns will not work - verify cache to fix.'),
                    parent=TK_ROOT,
                    icon=messagebox.ERROR,
                    title=gettext('BEE2 - Aperture Tag Files Missing'),
                )
                MUSIC_TAG_LOC = None
            else:
                MUSIC_TAG_LOC = tag_loc
                LOGGER.info('Ap-Tag dir: {}', tag_loc)

        if os.path.exists(mel_loc) and MUSIC_MEL_VPK is None:
            MUSIC_MEL_VPK = VPK(mel_loc)
            LOGGER.info('PS-Mel dir: {}', mel_loc)

        if MUSIC_MEL_VPK is not None and found_tag:
            break


def make_tag_coop_inst(tag_loc: str):
    """Make the coop version of the tag instances.

    This needs to be shrunk, so all the logic entities are not spread
    out so much (coop tubes are small).

    This way we avoid distributing the logic.
    """
    global TAG_COOP_INST_VMF
    TAG_COOP_INST_VMF = vmf = VMF.parse(
        os.path.join(tag_loc, TAG_GUN_COOP_INST)
    )

    ent_count = len(vmf.entities)

    def logic_pos() -> Iterator[Vec]:
        """Put the entities in a nice circle..."""
        while True:
            ang: float
            for ang in range(0, ent_count):
                ang *= 360/ent_count
                yield Vec(16*math.sin(ang), 16*math.cos(ang), 32)
    pos = logic_pos()
    # Move all entities that don't care about position to the base of the player
    for ent in vmf.entities:
        if ent['classname'] == 'info_coop_spawn':
            # Remove the original spawn point from the instance.
            # That way it can overlay over other dropper instances.
            ent.remove()
        elif ent['classname'] in ('info_target', 'info_paint_sprayer'):
            pass
        else:
            ent['origin'] = next(pos)

            # These originally use the coop spawn point, but this doesn't
            # always work. Switch to the name of the player, which is much
            # more reliable.
            if ent['classname'] == 'logic_measure_movement':
                ent['measuretarget'] = '!player_blue'

    # Add in a trigger to start the gel gun, and reset the activated
    # gel whenever the player spawns.
    trig_brush = vmf.make_prism(
        Vec(-32, -32, 0),
        Vec(32, 32, 16),
        mat='tools/toolstrigger',
    ).solid
    start_trig = vmf.create_ent(
        classname='trigger_playerteam',
        target_team=3,  # ATLAS
        spawnflags=1,  # Clients only
        origin='0 0 8',
    )
    start_trig.solids = [trig_brush]
    start_trig.add_out(
        # This uses the !activator as the target player so it must be via trigger.
        Output('OnStartTouchBluePlayer', '@gel_ui', 'Activate', delay=0, only_once=True),
        # Reset the gun to fire nothing.
        Output('OnStartTouchBluePlayer', '@blueisenabled', 'SetValue', 0, delay=0.1),
        Output('OnStartTouchBluePlayer', '@orangeisenabled', 'SetValue', 0, delay=0.1),
    )


def save():
    for gm in all_games:
        gm.save()
    CONFIG.save_check()


def load():
    global selected_game
    all_games.clear()
    for gm in CONFIG:
        if gm != 'DEFAULT':
            try:
                new_game = Game.parse(
                    gm,
                    CONFIG,
                )
            except ValueError:
                LOGGER.warning("Can't parse game: ", exc_info=True)
                continue
            all_games.append(new_game)
    if len(all_games) == 0:
        # Hide the loading screen, since it appears on top
        loadScreen.main_loader.suppress()

        # Ask the user for Portal 2's location...
        if not add_game(refresh_menu=False):
            # they cancelled, quit
            quit_application()
        loadScreen.main_loader.unsuppress()  # Show it again
    selected_game = all_games[0]


def add_game(e=None, refresh_menu=True):
    """Ask for, and load in a game to export to."""

    messagebox.showinfo(
        message=gettext(
            'Select the folder where the game executable is located ({appname})...'
        ).format(appname='portal2' + EXE_SUFFIX),
        parent=TK_ROOT,
        title=gettext('BEE2 - Add Game'),
        )
    exe_loc = filedialog.askopenfilename(
        title=gettext('Find Game Exe'),
        filetypes=[(gettext('Executable'), '.exe')],
        initialdir='C:',
        )
    if exe_loc:
        folder = os.path.dirname(exe_loc)
        gm_id, name = find_steam_info(folder)
        if name is None or gm_id is None:
            messagebox.showinfo(
                message=gettext('This does not appear to be a valid game folder!'),
                parent=TK_ROOT,
                icon=messagebox.ERROR,
                title=gettext('BEE2 - Add Game'),
                )
            return False

        # Mel doesn't use PeTI, so that won't make much sense...
        if gm_id == utils.STEAM_IDS['MEL']:
            messagebox.showinfo(
                message=gettext("Portal Stories: Mel doesn't have an editor!"),
                parent=TK_ROOT,
                icon=messagebox.ERROR,
                title=gettext('BEE2 - Add Game'),
            )
            return False

        invalid_names = [gm.name for gm in all_games]
        while True:
            name = tk_tools.prompt(
                gettext('BEE2 - Add Game'),
                gettext("Enter the name of this game:"),
                initialvalue=name,
            )
            if name in invalid_names:
                messagebox.showinfo(
                    icon=messagebox.ERROR,
                    parent=TK_ROOT,
                    message=gettext('This name is already taken!'),
                    title=gettext('BEE2 - Add Game'),
                    )
            elif name is None:
                return False
            elif name == '':
                messagebox.showinfo(
                    icon=messagebox.ERROR,
                    parent=TK_ROOT,
                    message=gettext('Please enter a name for this game!'),
                    title=gettext('BEE2 - Add Game'),
                    )
            else:
                break

        new_game = Game(name, gm_id, folder, {})
        all_games.append(new_game)
        if refresh_menu:
            add_menu_opts(game_menu)
        save()
        return True


def remove_game(e=None):
    """Remove the currently-chosen game from the game list."""
    global selected_game
    lastgame_mess = (
        gettext("\n (BEE2 will quit, this is the last game set!)")
        if len(all_games) == 1 else
        ""
    )
    confirm = messagebox.askyesno(
        title="BEE2",
        message=gettext('Are you sure you want to delete "{}"?').format(
                selected_game.name
            ) + lastgame_mess,
        )
    if confirm:
        selected_game.edit_gameinfo(add_line=False)
        selected_game.edit_fgd(add_lines=False)

        all_games.remove(selected_game)
        CONFIG.remove_section(selected_game.name)
        CONFIG.save()

        if not all_games:
            quit_application()  # If we have no games, nothing can be done

        selected_game = all_games[0]
        selectedGame_radio.set(0)
        add_menu_opts(game_menu)


def add_menu_opts(menu: Menu, callback=None):
    """Add the various games to the menu."""
    global selectedGame_radio, setgame_callback
    if callback is not None:
        setgame_callback = callback

    for ind in range(menu.index(END), 0, -1):
        # Delete all the old radiobutton
        # Iterate backward to ensure indexes stay the same.
        if menu.type(ind) == RADIOBUTTON:
            menu.delete(ind)

    for val, game in enumerate(all_games):
        menu.add_radiobutton(
            label=game.name,
            variable=selectedGame_radio,
            value=val,
            command=setGame,
        )
    setGame()


def setGame():
    global selected_game
    selected_game = all_games[selectedGame_radio.get()]
    setgame_callback(selected_game)


def set_game_by_name(name):
    global selected_game, selectedGame_radio
    for game in all_games:
        if game.name == name:
            selected_game = game
            selectedGame_radio.set(all_games.index(game))
            setgame_callback(selected_game)
            break

if __name__ == '__main__':
    Button(TK_ROOT, text='Add', command=add_game).grid(row=0, column=0)
    Button(TK_ROOT, text='Remove', command=remove_game).grid(row=0, column=1)
    test_menu = Menu(TK_ROOT)
    dropdown = Menu(test_menu)
    test_menu.add_cascade(menu=dropdown, label='Game')
    dropdown.game_pos = 0
    TK_ROOT['menu'] = test_menu

    load()
    add_menu_opts(dropdown, setgame_callback)
