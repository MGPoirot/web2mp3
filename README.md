# Web2mp3 - Music Download CLI

Command line interface to download audio from the internet:

1. with proper mp3 tagging
2. with proper ordering
3. able to download large scale

## How to use

After `python main.py` the interface is as follows:

```
YouTube URL or [Abort]? https://www.youtube.com/watch?v=NgE5mEQiizQ
Searching Spotify for    "Dirty South Hip Hop (feat. #1 Southern Hip Hop Music Instrumental) - Royalty Free Music - Topic"
                         1) Dirty South - PANDSHAFT
                         2) Dirty South Hip Hop (feat. #1 Southern Hip Hop Music Instrumental) - Royalty Free Music
Clear Spotify match      Dirty South Hip Hop (feat. #1 Southern Hip Hop Music Instrumental) - Royalty Free Music Instrumentals and Horror Soundscapes - Royalty Free Music

YouTube URL or [Abort]?
```

This identifies the song and takes about 1 second, after which you can provide a new url. You can also:

* call the function straight from CLI: `main.py https://www.youtube.com/watch?v=NgE5mEQiizQ`
* provide playlists: `main.py https://www.youtube.com/playlist?v=NgE5mEQiizQ`
* privode multiple urls, separated by spaces

In the background, audio is downloaded, and mp3 tags are applied.

## Supported platforms

currently only YouTube, but I'll add soundcloud soon

## Backbone

Starts with `youtube_search_python` to identify the video with the given URL. Then uses `spotipy` to get meta data. After which it uses `yt-dlp` to download audio, and finally `eye3d` for handling mp3 tags. `pytube` is optional to get a list of URLS from a playlist. 

Tested on Linux and Windows.

## Use agreement

Not to be used to download copyrighted audio.

