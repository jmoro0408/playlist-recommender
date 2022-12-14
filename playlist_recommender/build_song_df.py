import itertools
from pathlib import Path
from typing import Any

import pandas as pd

from playlist_recommender.spotipy_interaction import (
    SpotipyClient, read_client_id_and_secret, split_into_chunks)


def explode_results_list(result_list: list[tuple[Any, Any, Any]]) -> tuple:
    """breaks out the track_names, artist_names, track_ids.
    The original results list is of structure:
    list(tuple(track_name, artist_name, track_id))
    This func just breaks out the list of tuples into seperate lists.

    Returns:
        _type_: three lists of track_name, artist_name, track_ids
    """
    track_names = [x[0] for x in result_list]
    artist_names = [x[1] for x in result_list]
    track_ids = [x[2] for x in result_list]
    return track_names, artist_names, track_ids


def build_liked_song_df(sp: SpotipyClient) -> pd.DataFrame:
    """Return a dataframe with the users liked tracks,
    with track name, artist, and audio features for each track
    present in the users 'Liked songs'.

    +----------------+-------------+------------+
    | audio_features | artist_name | track_name |
    +----------------+-------------+------------+

    The web API only allows audio features requests of up to 100 tracks
    at a time, so the full liked songs json has to be split into 100
    track chunks before querying, then combined together.

    Args:
        sp (SpotipyClient): authorised spotipy client object

    Returns:
        pd.DataFrame: dataframe with track details
    """

    liked_tracks_json = sp.get_users_all_liked_tracks()
    parsed_liked_tracks_json = sp.parse_users_liked_tracks(liked_tracks_json)
    track_names, artist_names, track_ids = explode_results_list(
        parsed_liked_tracks_json
    )
    batch_size = 100  # API only allows up to 100 requests per batch
    track_id_chunks = list(split_into_chunks(track_ids, batch_size))
    audio_features = []
    for chunk in track_id_chunks:
        audio_features.append(sp.get_track_features(chunk))
    audio_features_flattened = list(
        itertools.chain.from_iterable(audio_features)
    )  # flattening list for df creation
    liked_song_df = pd.DataFrame(audio_features_flattened)
    liked_song_df["artist_names"] = artist_names
    liked_song_df["track_names"] = track_names
    return liked_song_df


def build_playlists_df(sp: SpotipyClient) -> pd.DataFrame:
    """builds the main playlist dataframe.
    For each track in each playlist the user has created, the function creates
    a dataframe with structure:
    +----------------+-------------+------------+---------------+
    | audio_features | artist_name | track_name | playlist_name |
    +----------------+-------------+------------+---------------+

    Args:
        sp (SpotipyClient): Athorized spotipy client object

    Returns:
        pd.DataFrame: df with track features for each user created playlist
    """
    user_playlists = sp.get_users_playlists_info()
    playlist_dfs_list = []
    batch_size = 100  # API only allows up to 100 requests per batch
    for playlist_name, playlist_id in user_playlists.items():
        audio_features_list = []
        playlist_tracks = sp.get_user_playlist_track_info(playlist_id)  # type: ignore
        playlist_tracks = [x for x in playlist_tracks if x[2] is not None]
        if len(playlist_tracks) == 0:
            continue
        track_names, artist_names, track_ids = explode_results_list(playlist_tracks)
        if len(playlist_tracks) > batch_size:
            track_id_chunks = list(split_into_chunks(track_ids, batch_size))
            for track_id_chunk in track_id_chunks:
                audio_features = sp.get_track_features(track_id_chunk)
                audio_features_list.append(audio_features)
                # Audio features fails when track_id list is all None.
                # This happens when a playlist is made up entirely of local files

        else:
            try:
                audio_features = sp.get_track_features(track_ids)
                audio_features_list.append(audio_features)
                # Audio features fails when track_id list is all None.
                # This happens when a playlist is made up entirely of local files
            except AttributeError:
                continue
        audio_features_flattened = list(
            itertools.chain.from_iterable(audio_features_list)
        )
        playlist_song_df = pd.DataFrame(audio_features_flattened)
        playlist_song_df["artist_names"] = artist_names
        playlist_song_df["track_names"] = track_names
        playlist_song_df["playlist_name"] = playlist_name
        playlist_dfs_list.append(playlist_song_df)
    playlists_df = pd.concat(playlist_dfs_list)
    playlists_df = playlists_df.reset_index(drop=True)
    return playlists_df


if __name__ == "__main__":
    client_id, client_secret = read_client_id_and_secret()
    sp = SpotipyClient(client_id, client_secret)
    liked_songs_df = build_liked_song_df(sp)
    playlists_df = build_playlists_df(sp)
    liked_songs_df.to_pickle(Path("playlist-recommender", "data", "liked_songs_df.pkl"))
    playlists_df.to_pickle(Path("playlist-recommender", "data", "playlist_df.pkl"))
