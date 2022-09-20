"""
The Database Wrapper Module.
"""

# pylint: disable=too-many-public-methods, too-many-lines
# pylint: disable=too-many-locals, too-many-arguments

import sqlite3
from typing import Dict, Optional, List, Union


class DBConnector:
    """The API for transacting with the local Databse.
    The database being used is a simple SQLite DB.
    Contains 1 table:
        1. caught_pokemons: Logs all the caught pokemons.
            Columns: [
                caught_on: timestamp | name: text | pokeid: Unique, Int |
                level: Int | iv: Real, Default 0.0 | category: text | nickname: text
            ]

    Attributes
    ----------
    db_path : str
        the path to the local database file.

    Methods
    -------
    assert_pokeid(pokeid)
        Checks if a row with the given pokeid exists in the DB.

    create_caught_table()
        Creates the caught pokemons table if it doesn't exist.

    delete_caught(pokeids)
        Deletes the row with the given pokeid from the DB.

    fetch_query(
        output_cols, level_min, level_max,
        iv_min, iv_max, order_by,
        limit, dup_count, kwargs
    )
        A generic SELECT based on a list of parameters.

    get_duplicates(count, output_cols)
        Get the duplicates (name) in the DB.

    get_ids(name)
        Get the pokeids for a given pokemon name.

    get_total(name)
        Get total number of pokemons (of given name if provided).

    get_trash(name, iv_threshold, max_dupes, output_cols)
        Get all the pokemons which are better to be sold away.

    insert_bulk(values)
        Insert multiple rows of pokemons

    insert_caught(
        caught_on, name,
        pokeid, level, iv,
        category, nickname
    )
        Insert a caught pokemon's details into the DB.

    reset_caught()
        Reset the caught_pokemons table.
    """
    def __init__(self, db_path: str = "pokeball.db"):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

    def create_caught_table(self):
        """
        Creates the pokemon logging table.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            caught_pokemons(
                caught_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                name TEXT NOT NULL,
                pokeid INTEGER NOT NULL UNIQUE,
                level INTEGER NOT NULL,
                iv REAL DEFAULT 0.0,
                category TEXT DEFAULT "common"
                    CHECK (
                        category IN ("common", "priority", "legendary", "shiny")
                    ) NOT NULL,
                nickname TEXT DEFAULT NULL
            );
            '''
        )
        self.conn.commit()

    def reset_caught(self):
        """
        Purges the pokemon log table.
        """
        self.cursor.execute(
            '''
            DELETE FROM caught_pokemons;
            '''
        )
        self.conn.commit()

    def delete_caught(self, pokeids: Union[int, list]):
        """
        Deletes the specified ID(s) from the pokemon log table.
        """
        if isinstance(pokeids, list):
            if len(pokeids) > 1:
                pokeid_str = f"IN {tuple(pokeids)}"
            elif len(pokeids) == 0:
                return
            else:
                pokeid_str = f"IS {pokeids[0]}"
        else:   # Single integer ID
            pokeid_str = f"IS {pokeids}"
        self.cursor.execute(
            f'''
            DELETE FROM caught_pokemons
            WHERE pokeid {pokeid_str};
            '''
        )
        self.conn.commit()

    # pylint: disable=invalid-name
    def insert_caught(
        self,
        caught_on: str, name: str, pokeid: int, level: int,
        iv: float = 0.0, category: str = "common",
        nickname: str = None
    ):
        """
        Logs a freshly caught pokemon.
        """
        self.cursor.execute(
            '''
            INSERT OR IGNORE INTO caught_pokemons
            (caught_on, name, pokeid, level, iv, category, nickname)
            VALUES
            (?, ?, ?, ?, ?, ?, ?);
            ''',
            (caught_on, name.title(), pokeid, level, iv, category, nickname)
        )
        self.conn.commit()

    def insert_bulk(self, values: List[Dict]):
        """
        Bulk log a batch of pokemons.
        """
        value_str = ',\n'.join(
            f'''(
                "{v['name'].title()}", {v['pokeid']}, {v['level']},
                {v['iv']}, "{v['category']}", "{v['nickname']}"
            )'''
            for v in values
        ).replace('"None"', 'null')

        self.cursor.execute(
            f'''
            INSERT OR IGNORE INTO caught_pokemons
            (name, pokeid, level, iv, category, nickname)
            VALUES
            {value_str}
            '''
        )
        self.conn.commit()
        self.cursor.execute(
            '''
            SELECT * FROM caught_pokemons
            WHERE pokeid > 2000
            '''
        )
        return self.cursor.fetchall()

    def get_ids(self, name: str) -> List:
        """
        Get the IDS for a specified pokemon name.
        """
        self.cursor.execute(
            '''
            SELECT pokeid FROM caught_pokemons
            WHERE name IS ?
            ''',
            (name.title(),)
        )
        return [res[0] for res in self.cursor.fetchall()]

    def assert_pokeid(self, pokeid: int) -> bool:
        """
        Verify whether a pokemon ID exists in the log.
        """
        self.cursor.execute(
            '''
            SELECT COUNT(*)
            FROM caught_pokemons
            WHERE pokeid IS ?
            ''',
            (pokeid,)
        )
        count = self.cursor.fetchone()[0]
        return count != 0

    def get_total(self, name: Optional[str] = None) -> int:
        """
        Get the total number of pokemons logged.
        A pokemon name can be provided to get its count.
        """
        if name:
            self.cursor.execute(
                '''
                SELECT COUNT(*) FROM caught_pokemons
                WHERE name IS ?
                GROUP BY name
                ''',
                (name.title(),)
            )
        else:
            self.cursor.execute(
                '''
                SELECT COUNT(*)
                FROM caught_pokemons
                '''
            )
        count = self.cursor.fetchone()
        if count:
            return count[0]
        return 0

    def fetch_query(
        self, output_cols: list = None, level_min: int = 0,
        level_max: int = 100, iv_min: int = 0,
        iv_max: int = 100.0, order_by: str = "name",
        limit: int = -1, dup_count: int = 0,
        **kwargs
    ) -> List:
        """
        Fetch ouput for a custom query based on the kwargs.
        """
        if not output_cols:
            output_cols = [
                "caught_on", "name", "pokeid", "level",
                "iv", "category", "nickname"
            ]
        output_cols_str = ', '.join(f'"{col}"' for col in output_cols)
        base = f"SELECT {output_cols_str} FROM caught_pokemons"
        for idx, (key, val) in enumerate(kwargs.items()):
            startword = 'WHERE' if idx == 0 else 'AND'
            if isinstance(val, list):
                if isinstance(val[0], str):
                    val_str = ','.join(f'"{v}"' for v in val)
                else:
                    val_str = ','.join(val)
                base += f"\n{startword} {key} IN ({val_str})"
            else:
                val_str = f'"{val}"' if isinstance(val, str) else val
                base += f"\n{startword} {key} IS {val_str}"
        startword = 'WHERE' if len(kwargs.items()) == 0 else 'AND'
        iv_str = f"\n{startword} iv BETWEEN {iv_min} AND {iv_max}"
        level_str = f"\nAND level BETWEEN {level_min} AND {level_max}"
        subquery = f'''
        SELECT DISTINCT name FROM caught_pokemons
        GROUP BY name
        HAVING COUNT(name) >= {dup_count}
        '''
        dup_str = f"\nAND name IN ({subquery})"
        if order_by.startswith('-'):
            order_by = f"{order_by[1:]} DESC"
        end = f"\nORDER BY {order_by}\nLIMIT {limit};"
        query = base + iv_str + level_str + dup_str + end
        self.cursor.execute(query)
        res = self.cursor.fetchall()
        res = [
            {
                col: poke[idx]
                for idx, col in enumerate(output_cols)
            }
            for poke in res
        ]
        return res

    def get_duplicates(
        self, count: int = 1,
        output_cols: list = None
    ) -> List:
        """
        Get a list of duplicate pokemons.
        A minimum count can be provided for the pokemon to be considered.
        """
        if not output_cols:
            output_cols = [
                "caught_on", "name", "pokeid", "level",
                "iv", "category", "nickname"
            ]
        self.cursor.execute(
            '''
            SELECT * FROM caught_pokemons
            WHERE name IN (
                SELECT DISTINCT name FROM caught_pokemons
                GROUP BY name
                HAVING COUNT(name) >= ?
            )
            ''',
            (count,)
        )
        res = self.cursor.fetchall()
        res = [
            {
                col: poke[idx]
                for idx, col in enumerate(output_cols)
            }
            for poke in res
        ]
        return res

    def get_trash(
        self, name: Optional[str] = None,
        iv_threshold: float = 100.0,
        max_dupes: int = None,
        output_cols: list = None,
        avoid: list = None
    ) -> List:
        """
        Get all pokemons, ready to be mass sold/released.
        """
        if not output_cols:
            output_cols = [
                "caught_on", "name", "pokeid", "level",
                "iv", "category", "nickname"
            ]
        output_cols_str = ', '.join(f'"{col}"' for col in output_cols)
        if name:
            if avoid and name in avoid:
                return []
            name = name.title()
            if self.get_total(name=name) > 1:
                subquery = f'("{name}")'
            else:
                return []
        else:
            self.cursor.execute(
                f'''
                SELECT DISTINCT name FROM caught_pokemons
                GROUP BY name
                HAVING COUNT(name) > {1 if max_dupes and max_dupes > 0 else 0}
                '''
            )
            subquery = self.cursor.fetchall()
            subquery = tuple(
                elem[0]
                for elem in subquery
                if elem[0] not in avoid
            )
        if len(subquery) == 0:
            return []
        if max_dupes is None:
            max_dupes = 0
        self.cursor.execute(
            f'''
            SELECT {output_cols_str}
            FROM caught_pokemons AS T1
            WHERE T1.pokeid IN (
                SELECT T2.pokeid
                FROM caught_pokemons T2
                WHERE
                    T2.name = T1.name
                AND
                    iv < ?
                AND
                    nickname IS NULL
                AND
                    category IS "common"
                AND
                    pokeid <> 1
                AND
                    name in {subquery}
                ORDER BY iv DESC
                LIMIT -1
                OFFSET MAX(0, ?)
            )
            ORDER BY T1.pokeid DESC;
            ''',
            (iv_threshold, max_dupes)
        )
        res = self.cursor.fetchall()
        res = [
            {
                col: poke[idx]
                for idx, col in enumerate(output_cols)
            }
            for poke in res
        ]
        return res


if __name__ == "__main__":
    dbconn = DBConnector(db_path='data/pokeball.db')
