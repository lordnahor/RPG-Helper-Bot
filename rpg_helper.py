'''The main RPG helper logic. Receives commands, and returns responses.'''
import json
import os
from random import randint

import regex as re

STAT_ORDER = ["str", "dex", "con", "int", "wis", "cha"]

class Stats(dict):
    '''Special dictionary to parse stats and create modifiers automatically.'''
    def __init__(self, from_dict):
        super().__init__()
        for key, value in from_dict.items():
            self[key] = value

    def __setitem__(self, key, value):
        '''If special attribute is set, create the mod version of it.'''
        if key in set(["strmod", "dexmod", "conmod",
                       "intmod", "wismod", "chamod"]):
            # Can be caused by a reload. Do not allow these keys to be set
            # directly. They are always calculated.
            # Cannot use them as properties instead because I need them to be
            # key value entries for macro formating.
            return
        if key in set(["str", "dex", "con", "int", "wis", "cha"]):
            super().__setitem__(key + "mod", Stats.get_modifier(value))
        super().__setitem__(key, value)

    @staticmethod
    def get_modifier(value):
        '''Generate the attribute mod (as string).'''
        mod = int(value/2) - 5
        return str(mod) if mod < 0 else f"+{mod}"


class RPGHelper():
    '''Main RPG helper class.'''
    def __init__(self, game):
        # All the macros for the game.
        self.macros = dict()
        # All the slack/discord uuids are mapped to a list of characters.
        self.user_to_characters = dict()
        # The default character for each user.
        self.user_default = dict()
        # The stats of each character.
        self.characters = dict()
        # The game being played.
        self.game = None
        if game:
            self.load_game(game)

    def save_game(self):
        '''Save the characters and macros for a game.'''
        if not self.game:
            return
        json.dump(
            self.characters,
            open(f"{self.game}/characters.json", "w"),
            sort_keys=True, indent=4, separators=(',', ': '))
        json.dump(
            self.user_to_characters,
            open(f"{self.game}/user_to_characters.json", "w"),
            sort_keys=True, indent=4, separators=(',', ': '))
        json.dump(
            self.user_default,
            open(f"{self.game}/user_default.json", "w"),
            sort_keys=True, indent=4, separators=(',', ': '))

    def load_game(self, game):
        '''Loads a new game from the folder with name {game}'''
        was_loaded = self.game
        if not os.path.exists(f"{game}"):
            return f"Game path {game} does not exist"
        self.macros = json.load(open(f"{game}/macros.json"))
        self.user_to_characters = (
            json.load(open(f"{game}/user_to_characters.json"))
            if os.path.exists(f"{game}/user_to_characters.json") else
            dict())
        self.user_default = (
            json.load(open(f"{game}/user_default.json"))
            if os.path.exists(f"{game}/user_default.json") else
            dict())
        self.characters = {
            name: Stats(stats)
            for name, stats in json.load(
                open(f"{game}/characters.json")).items()
        } if os.path.exists(f"{game}/characters.json") else dict()
        self.game = game

        if was_loaded:
            return f"Game {was_loaded} was replaced with game {game}"
        return f"New game {game} loaded"

    def handle_command(self, user, message):
        '''Parse and execute slack/discord message and respond if needed.'''
        parse = re.match(r"!([a-zA-Z0-9_\-]+?)\s+(.*)$", message)

        if not parse:
            # Not a message that the bot needs to respond to.
            return None
        command, args = parse.groups()
        if command == "load":
            # Loads a new game with new characters and macros.
            return self.load_game(args)

        if not self.game:
            # Rest of the commands need a game loaded.
            return (
                "No game has been loaded. "
                "Load using command `!load <game>`")

        response = None
        if command == "roll":
            # Rolls a particular stat. parameter user is the initiator.
            response = self.handle_roll(user, args)
        elif command == "character":
            response = self.handle_character(user, args)
        elif command == "macro":
            response = self.handle_macro(user, args)
        return response

    def handle_macro(self, user, command):
        '''Add or delete macros to characters for user'''
        # !macro add foggy unarmed_atk !roll d20{dex}{proficiency}
        userkey = str(user)
        if userkey not in self.user_to_characters:
            return f"<@{user}> does not have characters to add/del macros to."

        parts = command.split()
        try:
            macro_command, character, name = parts[:3]
        except ValueError:
            return f"Cannot parse command {command}."

        if character not in self.user_to_characters[userkey]:
            return (f"<@{user}> does not have character "
                    f"{character} to add/del macros to.")
        if macro_command == "add":
            return self.add_macro(character, name, " ".join(parts[3:]))
        if macro_command == "del":
            return self.del_macro(character, name)
        return f"Unknown macro subcommand received: {macro_command}."

    def add_macro(self, character, name, macro):
        '''Adds a personal new macro'''
        self.characters[character].setdefault("macros", dict())[name] = macro
        self.save_game()
        return f"Successfully added new macro {name} to {character}."

    def del_macro(self, character, name):
        '''Deletes an existing macro if it exists'''
        if name in self.characters[character]["macros"]:
            del self.characters[character]["macros"][name]
            return f"Successfully deleted macro {name} from {character}."
        return f"Did not find macro {name} in {character}."

    def handle_character(self, user, command):
        '''Add or delete characters for user.'''
        parse = re.match(r"(add|del|show)\s+(.*)$", command)
        if not parse:
            return f"Did not understand {command}."
        char_command, args = parse.groups()
        if char_command == "del":
            if self.delete_character(user, args):
                return f"Deleted character {args}"
        if char_command == "add":
            return self.add_character(user, args)
        if char_command == "show":
            return self.show_character(user, args)
        return f"Did not understand {command}."

    def delete_character(self, user, name):
        '''Delete character {name} for {user}.'''
        userkey = str(user)
        if userkey not in self.user_to_characters:
            return f"<@{user}> does not have characters."
        if name not in self.user_to_characters[userkey]:
            return f"<@{user}> does not have a character by name: {name}."
        if name not in self.characters:
            return f"Error trying to delete character {name} for <@{user}>"

        del self.characters[name]
        self.user_to_characters[userkey].remove(name)
        if not self.user_to_characters[userkey]:
            # The user has no characters and is not needed anymore.
            del self.user_to_characters[userkey]
            del self.user_default[userkey]
        if (userkey in self.user_to_characters
                and self.user_default[userkey] == name):
            # Switching defaults if the delete was the default character.
            self.user_default[userkey] = self.user_to_characters[0]
        self.save_game()
        return f"Successfully deleted {name} for <@{user}>"

    def add_character(self, user, args):
        '''Parse and add character for {user}'''
        userkey = str(user)
        try:
            name, stats, proficients, hitdice, level = args.split()
        except ValueError:
            raise RuntimeError(f"Unable to parse character ({args})")
        if (name in self.characters
                and not (userkey in self.user_to_characters
                         and name in self.user_to_characters[userkey])):
            return (f"Cannot recreate {name} for <@{user}>"
                    f"as it is already assigned to some other player.")
        old_macros = (
            self.characters[name]["macros"]
            if name in self.characters else
            dict())

        stat_map = Stats({
            "name": name,
            "proficient_rolls": proficients.split(","),
            "level": int(level),
            "macros": old_macros,
            "hitdice": int(hitdice)
        })
        stats_list = stats.split(",")
        try:
            for i, stat_name in enumerate(STAT_ORDER):
                stat_map[stat_name] = int(stats_list[i])
        except IndexError:
            return f"Unable to parse character stats ({stats})"
        except ValueError:
            return f"Unable to parse character stats ({stats})"

        self.characters[name] = stat_map
        self.user_to_characters.setdefault(userkey, list()).append(name)
        self.user_default.setdefault(userkey, name)
        self.save_game()
        return f"Successfully created character {name} for <@{user}>"

    def show_character(self, user, name):
        if name in self.characters:
            return f"```{json.dumps(self.characters[name], indent=4, sort_keys=True)}```"
        return f"Did not find a character with the name: {name}"

    def handle_roll(self, user, roll_command):
        '''Responds to a roll command by {user}.'''
        try:
            return self.roll(user, *self.resolve_command(user, roll_command))
        except RuntimeError as rt_err:
            return " ".join(map(str, rt_err.args))

    def resolve_command(self, user, roll_command):
        '''Resolves a macro, if a macro is detected.'''
        userkey = str(user)
        if userkey not in self.user_to_characters:
            # The user is not in the list, and does not have
            # stats to roll from. Hopefully this command does
            # not need to be resolved.
            return "UNKNOWN", roll_command
        parts = roll_command.split()
        # check if character resolution must happen.
        character = self.user_default[userkey]
        specific_character = False
        if parts[0].strip() in self.characters:
            if parts[0].strip() in self.user_to_characters[userkey]:
                specific_character = True
                character = parts[0].strip()
            else:
                raise RuntimeError(
                    f"<@{user}> cannot roll for {parts[0].strip()}")

        roll_command = (
            " ".join(parts[1:]) if specific_character else roll_command)

        stats = self.characters[character]
        prof = RPGHelper.get_proficiency_by_level(stats["level"])
        parse = re.match(r"(.*?)(\s+[A|D])?$", roll_command)
        if not parse:
            # Unknown command, the roll function will deal with it.
            return character, roll_command
        command, adv_or_disadv = parse.groups()
        if command in self.macros:
            # Resolve the macro format with the key values
            # in the stats dictionary.
            return character, self.macros[command].format(
                **stats,
                is_proficient=(
                    prof if command in stats["proficient_rolls"] else ""),
                proficiency=prof,
                adv_or_disadv=adv_or_disadv if adv_or_disadv else "")
        if ("macros" in self.characters[character]
                and command in self.characters[character]["macros"]):
            # Resolve the macro format with the key values
            # in the stats dictionary.
            return (
                character, self.characters[character]["macros"][command].format(
                    **stats,
                    is_proficient=(
                        prof if command in stats["proficient_rolls"] else ""),
                    proficiency=prof,
                    adv_or_disadv=adv_or_disadv if adv_or_disadv else ""))
        # It is not a known macro.
        return character, roll_command

    @staticmethod
    def get_proficiency_by_level(level):
        '''Gets the proficiency modifier based on level of character.'''
        return f"+{int((level - 1) / 4) + 2}"

    @staticmethod
    def roll(user, character, roll_command):
        '''Rolls a command resolved to the base form EG. d20+2 A'''
        parse = re.match(
            r"([0-9]*)d([0-9]+)\s*([+\-]\s*[0-9]+)*(\s+[A|D])?",
            roll_command.strip())
        if not parse:
            return f"<@{user}> Unknown command: {roll_command}"

        # Forget the third group as by default only the last capture of it
        # is read and returned
        number, sides, _, adv = parse.groups()
        # Here we actually read all the captures. (Regex is the best!)
        constants = parse.captures(3)

        # Default number is 1. Eg. d20 resolves to 1d20.
        number = int(number) if number else 1
        # Pray to RNGesus.
        rolls = [randint(1, int(sides)) for i in range(int(number))]
        # Needed if Adv or Disadv is required.
        rerolls = [randint(1, int(sides)) for i in range(int(number))]
        if adv:
            adv = adv.strip()
        if adv == "A" and sum(rerolls) > sum(rolls):
            true_rolls = rerolls
        elif adv == "D" and sum(rerolls) < sum(rolls):
            true_rolls = rerolls
        else:
            true_rolls = rolls
        # Adding true_rolls and all constants parsed.
        total = sum(
            true_rolls + [
                int(re.sub(r"\s+", "", constant))
                for constant in constants
                if constant
            ]
        )
        if adv:
            # The format of the response when A or D was set.
            adv_text = "ADV" if adv == "A" else "DISADV"
            return (
                f"<@{user}> rolled `{roll_command}` for {character}\n"
                f"```"
                f"{repr(rolls)}, {repr(rerolls)}\n"
                f"Total ({adv_text}): {total}"
                f"```")
        # The format of the response when A or D was not set.
        return (f"<@{user}> rolled `{roll_command}` for {character}\n"
                f"```"
                f"{repr(rolls)}\n"
                f"Total: {total}"
                f"```")
