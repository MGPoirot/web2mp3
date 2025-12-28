from initialize import index_path, Path
from utils import input_is
from utils import json_out, json_in
from typing import List
import json


def uri2path(uri: str | Path) -> Path:
    """
    Converts a URI string to a Path object pointing to the storage location.

    This function takes a URI string or a Path object and converts it into
    a Path object that represents the full path to the file in the storage
    location. For example, if the URI is 'platform.KEivybw89gyiv', the
    function returns a Path object representing
    'INDEX_PATH/platform.KEivybw89gyiv'.

    :param uri:     A URI string or a Path object to be converted.
    :return:        A Path object pointing to the full storage path.
    """
    path = uri if isinstance(uri, Path) else index_path / uri
    return path


def has_uri(uri: str | Path) -> bool:
    """
    Checks if the file corresponding to the URI exists in the index.

    :param uri:     A URI string or Path object representing the index item.
    :return:        True if the file exists, False otherwise.
    """
    return uri2path(uri).is_file()


def read(uri: str | Path) -> dict | None:
    """
    Reads and returns the content of a JSON file from the index.

    :param uri:     A URI string or Path object representing the index item.
    :return:        A dictionary with the JSON content if the file is not empty,
                    or `None` if the file is empty.
    """
    path = uri2path(uri)
    return None if is_empty(path) else json_in(path)


def is_empty(path: Path) -> bool:
    """
    Checks if a file is empty.

    :param path:    A Path object representing the file to check.
    :return:        `True` if the file is empty, `False` otherwise.
    """
    return path.stat().st_size == 0


def to_do() -> List[str]:
    """
    Retrieves a list of non-empty URIs from the index.

    :return:    A list of URI strings corresponding to non-empty files in the index.
    """
    return [f.name for f in index_path.rglob("*") if not is_empty(f)]


def write(
        uri: str | Path,
        tags: dict | None = None,
        settings: dict | None = None,
        overwrite: bool = True,
) -> None:
    """
    Writes a value to a key (short URL) in the index.

    :param uri:         A URI string or Path object representing the index item.
    :param tags:        A dictionary of tags to associate with the key (default: `None`).
    :param settings:    A dictionary of settings to associate with the key (default: `None`).
    :param overwrite:   A boolean indicating whether to overwrite existing data (default: `True`).

    :return:            None.
    """
    path = uri2path(uri)
    if not overwrite and has_uri(path):
        return
    payload = {'tags': tags, 'settings': settings}
    json_out(payload, path) if any(payload.values()) else open(path, 'w').close()


def debug() -> None:
    """
    Provides an interactive interface for debugging and managing the index.

    This function allows the user to:
    - View statistics about the index (number of records, processed/unprocessed records).
    - View detailed information about individual items in the database.
    - Delete or clear items from the database.

    It includes the following helper functions:
    - `_pretty_print(uri)`: Pretty-prints the JSON content of a given URI.
    - `_pop_uri_from_index(uri)`: Deletes an index item of to the URI.

    :return: None.
    """

    def _pretty_print(uri: str | Path) -> None:
        """
        Pretty-prints the content of the and index item for a specified URI.

        :param uri: A URI string or Path object representing the index item.
        :return: None.
        """
        print(json.dumps(read(uri2path(uri)), indent=4, sort_keys=True))

    def _pop_uri_from_index(uri: str | Path) -> None:
        """
        Deletes the index item and prints a confirmation message.

        :param uri: A URI string or Path object of the index item to be deleted.
        :return: None.
        """
        uri2path(uri).unlink()
        print(f'Deleted index item "{uri}"')

    # Get statistics of the index
    n_records = len(list(index_path.glob('*')))  # Number of URIs in the index
    uris_to_do = to_do()  # List of unprocessed URIs
    n_to_do = len(uris_to_do)  # Number of unprocessed items
    n_empty_records = n_records - n_to_do  # Number of processed (empty) URIs

    # Structure the meta information to print
    info = [
        ('number of processed records', n_empty_records),
        ('number of unprocessed records', n_to_do),
        ('location', index_path),
    ]

    # Print header and the index meta information
    print('INDEX INFORMATION:',
          *['\n- {}{}'.format(k.ljust(30), str(v).rjust(6)) for k, v in info]
          )

    # Early return if there are no URIs non-empty URIs to inspect
    if not n_to_do:
        return

    # Allow the user to choose between viewing a list of items or one by one
    look_closer = input('>>> Do you want to see a list of items,'
                        ' or check per item? List / Item / [No]  ')

    # Early return if the user did not choose to inspect
    if not input_is('List', look_closer) and not input_is('Item', look_closer):
        return

    # Process the user request to inspect URIs
    for i, uri in enumerate(uris_to_do):
        path = uri2path(uri)

        # Display item details
        print(f'{str(i + 1).rjust(3)}/{n_to_do}:', path.name)
        _pretty_print(path)

        # Let the user decide whether to delete or empty an item
        if input_is('Item', look_closer):
            do_pop = input(
                '>>> Do you want to permanently delete or clear this '
                'item from the index? Delete / Clear / [No]  ')
            if input_is('Delete', do_pop):
                _pop_uri_from_index(path)  # Delete the item
                msg = 'deleted'
            elif input_is('Clear', do_pop):
                write(
                    path)  # Clear the item (write an empty record)
                msg = 'cleared'
            else:
                msg = 'untouched'
            print(f'Index entry {msg}.')


if __name__ == '__main__':
    debug()
