from dotenv import load_dotenv
from httpx import AsyncClient
from os import getenv
import asyncio
from typing import Dict
LastFMurl = "https://ws.audioscrobbler.com/2.0/"


class LastFMError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


LASTFM_ERRORS = {
    6: "User/artist not found",
    8: "Backend issue",
    17: "Users privacy settings blocking this request",
    26: "Access for your account has been suspended, please contact Last.fm",
    13: "Invalid method signature supplied",
    16: "There was a temporary error processing your request. Please try again",
    29: "Rate limit exceeded",
    10: "Invalid API key",
    11: "Service Offline - This service is temporarily offline. Try again later.",
    3: "Invalid method - No method with that name in this package",
    4: "Authentication Failed - You do not have permissions to access the service",
    5: "Invalid format - This service doesn't exist in that format",
    7: "Invalid parameters - Your request is missing a required parameter",
    9: "Invalid resource specified",
    15: "This token has not been authorized",
    18: "There was a temporary error processing your request. Please try again",
    19: "You must be logged in to do that",
    20: "This operation requires authentication",
    21: "You do not have permissions to access the service",
    22: "There was a temporary error processing your request. Please try again",
    23: "Operation failed - Most likely the backend service failed. Please try again.",
    24: "Invalid session key - Please re-authenticate",
}

class LastFM:
    def __init__(self):
        load_dotenv(".env")
        self.session = AsyncClient()

    async def request(self, request: Dict, paramater: str = None, **kwargs: dict):
        response = await self.session.get(
            url=LastFMurl,
            params={
                "api_key": getenv("LASTFM_APIKEY"),
                "format": "json",
                **request,
            },
        )
        data = response.json()
        if "errors" in data:
            raise LastFMError(f"Error: {LASTFM_ERRORS[data.get('error')]}")
        if paramater and not data.get(paramater):
            raise LastFMError(f"Error: {paramater} not found")
        return data

    async def profile(self, username: str):
        response = await self.request({"method": "user.getInfo", "username": username})
        return {
            "url": response["user"]["url"],
            "username": response["user"]["name"],
            "government": response["user"]["realname"] or None,
            "avatar": response["user"]["image"][-1]["#text"].replace(".png", ".gif")
            or None,
            "library": {
                "scrobbles": int(response["user"]["playcount"]),
                "artists": int(response["user"]["artist_count"]),
                "albums": int(response["user"]["album_count"]),
                "tracks": int(response["user"]["track_count"]),
            },
            "meta": {
                "registered": response["user"]["registered"]["#text"],
                "country": response["user"]["country"] or None,
                "age": int(response["user"]["age"]),
                "pro": response["user"]["type"] == "subscriber",
            },
        }

    async def now_playing(self, username: str):
        tracks = await self.request(
            {"method": "user.getRecentTracks", "username": username, "limit": 1},
            "recenttracks",
        )
        track, _track = (
            tracks["recenttracks"]["track"][0],
            tracks["recenttracks"]["track"][0],
        )
        tasks = list()
        tasks.append(
            self.request(
                {"method": "user.getInfo", "username": username},
                "user",
            )
        )
        tasks.append(
            self.request(
                {
                    "method": "track.getInfo",
                    "username": username,
                    "artist": track["artist"]["#text"],
                    "track": track["name"],
                },
                "track",
            )
        )
        tasks.append(
            self.request(
                {
                    "method": "artist.getInfo",
                    "username": username,
                    "artist": track["artist"]["#text"],
                },
                "artist",
            )
        )
        if track["album"]["#text"]:
            tasks.append(
                self.request(
                    {
                        "method": "album.getInfo",
                        "username": username,
                        "artist": track["artist"]["#text"],
                        "album": track["album"]["#text"],
                    },
                    "album",
                )
            )
        else:
            pass

        user, track, artist, album = await asyncio.gather(*tasks)
        track = track["track"]
        user = user["user"]
        artist = artist["artist"]
        response = {
            "url": track["url"],
            "name": track["name"],
            "image": {
                "url": _track["image"][-1]["#text"],
            }
            if _track["image"][-1].get("#text")
            else None,
            "plays": int(track["userplaycount"]),
            "playing": not bool(_track.get("date")),
            "artist": {
                "url": artist["url"],
                "name": artist["name"],
                "image": artist["image"][-1]["#text"] or None,
                "plays": int(artist["stats"]["userplaycount"]),
            },
        }
        if album:
            album = album["album"]
            response["album"] = {
                "url": album["url"],
                "name": album["name"],
                "image": album["image"][-1]["#text"] or None,
                "plays": int(album["userplaycount"]),
                "tracks": [
                    {
                        "url": _track["url"],
                        "name": _track["name"],
                    }
                    for _track in album["tracks"]["track"]
                ]
                if album.get("tracks")
                and not isinstance(album["tracks"]["track"], dict)
                else [],
            }
        response["user"] = {
            "url": user["url"],
            "username": user["name"],
            "full_name": user["realname"] or None,
            "avatar": user["image"][-1]["#text"].replace(".png", ".gif") or None,
            "library": {
                "scrobbles": int(user["playcount"]),
                "artists": int(user["artist_count"]),
                "albums": int(user["album_count"]),
                "tracks": int(user["track_count"]),
            },
            "meta": {
                "registered": user["registered"]["#text"],
                "country": (user["country"] if user["country"] != "None" else None),
                "age": int(user["age"]),
                "pro": user["type"] == "subscriber",
            },
        }
        return response

    async def get_artist(self, artist: str):
        response = await self.request(
            {"method": "artist.getInfo", "artist": artist}, "artist"
        )
        return {
            "url": response["artist"]["url"],
            "name": response["artist"]["name"],
            "image": response["artist"]["image"][-1]["#text"] or None,
            "plays": int(response["artist"]["stats"]["userplaycount"]),
            "listeners": int(response["artist"]["stats"]["listeners"]),
            "playcount": int(response["artist"]["stats"]["playcount"]),
            "bio": response["artist"]["bio"]["content"],
            "tags": [
                {"name": tag["name"], "url": tag["url"]}
                for tag in response["artist"]["tags"]["tag"]
            ],
            "similar": [
                {"name": artist["name"], "url": artist["url"]}
                for artist in response["artist"]["similar"]["artist"]
            ],
            "tracks": [
                {"name": track["name"], "url": track["url"]}
                for track in response["artist"]["toptracks"]["track"]
            ],
            "albums": [
                {"name": album["name"], "url": album["url"]}
                for album in response["artist"]["topalbums"]["album"]
            ],
        }

    async def recent_tracks(self, username: str, limit: int = 1000):
        response = await self.request(
            {
                "method": "user.getRecentTracks",
                "username": username,
                "limit": limit,
                "autoscorrect": 1,
            },
            "recenttracks",
        )
        return [
            {
                "url": track["url"],
                "name": track["name"],
                "image": {
                    "url": track["image"][-1]["#text"],
                }
                if track["image"][-1].get("#text")
                else None,
                "plays": int(track["userplaycount"]),
                "playing": not bool(track.get("date")),
                "artist": {
                    "url": track["artist"]["url"],
                    "name": track["artist"]["#text"],
                    "image": track["artist"]["image"][-1]["#text"] or None,
                    "plays": int(track["artist"]["stats"]["userplaycount"]),
                },
            }
            for track in response["recenttracks"]["track"]
        ]

    async def get_album(self, artist: str, album: str):
        response = await self.request(
            {
                "method": "album.getInfo",
                "artist": artist,
                "album": album,
            },
            "album",
        )
        return {
            "url": response["album"]["url"],
            "name": response["album"]["name"],
            "image": response["album"]["image"][-1]["#text"] or None,
            "plays": int(response["album"]["userplaycount"]),
            "artist": {
                "url": response["album"]["artist"]["url"],
                "name": response["album"]["artist"]["name"],
            },
            "tracks": [
                {
                    "url": track["url"],
                    "name": track["name"],
                    "duration": int(track["duration"]),
                }
                for track in response["album"]["tracks"]["track"]
            ],
            "tags": [
                {"name": tag["name"], "url": tag["url"]}
                for tag in response["album"]["tags"]["tag"]
            ],
        }

    async def top_artists(self, username: str, period: str, limit: int = 1000):
        response = await self.request(
            {
                "method": "user.getTopArtists",
                "username": username,
                "period": period,
                "limit": limit,
            },
            "topartists",
        )
        return [
            {
                "url": artist["url"],
                "name": artist["name"],
                "image": artist["image"][-1]["#text"] or None,
                "plays": int(artist["playcount"]),
            }
            for artist in response["topartists"]["artist"]
        ]

    async def top_tracks(self, username: str, period: str, limit: int = 1000):
        response = await self.request(
            {
                "method": "user.getTopTracks",
                "username": username,
                "period": period,
                "limit": limit,
            },
            "toptracks",
        )
        return [
            {
                "url": track["url"],
                "name": track["name"],
                "image": track["image"][-1]["#text"] or None,
                "plays": int(track["playcount"]),
                "artist": {
                    "url": track["artist"]["url"],
                    "name": track["artist"]["name"],
                },
            }
            for track in response["toptracks"]["track"]
        ]

    async def top_albums(self, username: str, period: str, limit: int = 1000):
        response = await self.request(
            {
                "method": "user.getTopAlbums",
                "username": username,
                "period": period,
                "limit": limit,
            },
            "topalbums",
        )
        return [
            {
                "url": album["url"],
                "name": album["name"],
                "image": album["image"][-1]["#text"] or None,
                "plays": int(album["playcount"]),
                "artist": {
                    "url": album["artist"]["url"],
                    "name": album["artist"]["name"],
                },
            }
            for album in response["topalbums"]["album"]
        ]

    async def get_album(self, username: str, album: str):
        response = await self.request(
            {
                "method": "album.getInfo",
                "username": username,
                "album": album,
            },
            "album",
        )
        return {
            "url": response["album"]["url"],
            "name": response["album"]["name"],
            "image": response["album"]["image"][-1]["#text"] or None,
            "plays": int(response["album"]["userplaycount"]),
            "artist": {
                "url": response["album"]["artist"]["url"],
                "name": response["album"]["artist"]["name"],
            },
            "tracks": [
                {
                    "url": track["url"],
                    "name": track["name"],
                    "duration": int(track["duration"]),
                }
                for track in response["album"]["tracks"]["track"]
            ],
            "tags": [
                {"name": tag["name"], "url": tag["url"]}
                for tag in response["album"]["tags"]["tag"]
            ],
        }

    async def get_track(self, username: str, artist: str, track: str):
        response = await self.request(
            {
                "method": "track.getInfo",
                "username": username,
                "artist": artist,
                "track": track,
            },
            "track",
        )
        return {
            "url": response["track"]["url"],
            "name": response["track"]["name"],
            "image": response["track"]["image"][-1]["#text"] or None,
            "plays": int(response["track"]["userplaycount"]),
            "artist": {
                "url": response["track"]["artist"]["url"],
                "name": response["track"]["artist"]["name"],
            },
            "album": {
                "url": response["track"]["album"]["url"],
                "name": response["track"]["album"]["name"],
            },
            "tags": [
                {"name": tag["name"], "url": tag["url"]}
                for tag in response["track"]["toptags"]["tag"]
            ],
        }

    async def get_tag(self, tag: str):
        response = await self.request(
            {
                "method": "tag.getInfo",
                "tag": tag,
            },
            "tag",
        )
        return {
            "url": response["tag"]["url"],
            "name": response["tag"]["name"],
            "wiki": response["tag"]["wiki"]["content"],
            "image": response["tag"]["image"][-1]["#text"] or None,
            "reach": int(response["tag"]["reach"]),
            "total": int(response["tag"]["total"]),
            "top_artists": [
                {"name": artist["name"], "url": artist["url"]}
                for artist in response["tag"]["topartists"]["artist"]
            ],
            "top_albums": [
                {"name": album["name"], "url": album["url"]}
                for album in response["tag"]["topalbums"]["album"]
            ],
            "top_tracks": [
                {"name": track["name"], "url": track["url"]}
                for track in response["tag"]["toptracks"]["track"]
            ],
        }

    async def library_artists(self, username: str, period: str, limit: int = 1000):
        response = await self.request(
            {
                "method": "user.getTopArtists",
                "username": username,
                "period": period,
                "limit": limit,
            },
            "topartists",
        )
        return [
            {
                "url": artist["url"],
                "name": artist["name"],
                "image": artist["image"][-1]["#text"] or None,
                "plays": int(artist["playcount"]),
            }
            for artist in response["topartists"]["artist"]
        ]

    async def library_tracks(self, username: str, period: str, limit: int = 1000):
        response = await self.request(
            {
                "method": "user.getTopTracks",
                "username": username,
                "period": period,
                "limit": limit,
            },
            "toptracks",
        )
        return [
            {
                "url": track["url"],
                "name": track["name"],
                "image": track["image"][-1]["#text"] or None,
                "plays": int(track["playcount"]),
                "artist": {
                    "url": track["artist"]["url"],
                    "name": track["artist"]["name"],
                },
            }
            for track in response["toptracks"]["track"]
        ]

    async def library_albums(self, username: str, period: str, limit: int = 1000):
        response = await self.request(
            {
                "method": "user.getTopAlbums",
                "username": username,
                "period": period,
                "limit": limit,
            },
            "topalbums",
        )
        return [
            {
                "url": album["url"],
                "name": album["name"],
                "image": album["image"][-1]["#text"] or None,
                "plays": int(album["playcount"]),
                "artist": {
                    "url": album["artist"]["url"],
                    "name": album["artist"]["name"],
                },
            }
            for album in response["topalbums"]["album"]
        ]

    async def library_tags(self, username: str, period: str, limit: int = 1000):
        Response = await self.request(
            {
                "method": "user.getTopTags",
                "username": username,
                "period": period,
                "limit": limit,
            },
            "toptags",
        )
        return [
            {"name": tag["name"], "url": tag["url"]}
            for tag in Response["toptags"]["tag"]
        ]

    async def library(self, username: str):
        tasks = list()
        tasks.append(self.library_artists(username, "overall"))
        tasks.append(self.library_albums(username, "overall"))
        tasks.append(self.library_tracks(username, "overall"))
        tasks.append(self.library_tags(username, "overall"))
        artists, albums, tracks, tags = await asyncio.gather(*tasks)
        return {
            "artists": artists,
            "albums": albums,
            "tracks": tracks,
            "tags": tags,
        }
