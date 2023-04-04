# Web2mp3 - Music Download CLI

A scalable command line interface to download music from the internet with proper mp3 tagging and directory structuring.
## How to use

Easies is calling `python main.py`:

```python
YouTube URL or [Abort]? https://www.youtube.com/watch?v=NgE5mEQiizQ
Searching Spotify for    "Dirty South Hip Hop (feat. #1 Southern Hip Hop Music Instrumental) - Royalty Free Music - Topic"
                         1) Dirty South - PANDSHAFT
                         2) Dirty South Hip Hop (feat. #1 Southern Hip Hop Music Instrumental) - Royalty Free Music
Clear Spotify match      Dirty South Hip Hop (feat. #1 Southern Hip Hop Music Instrumental) - Royalty Free Music Instrumentals and Horror Soundscapes - Royalty Free Music

YouTube URL or [Abort]?
```

The following should take about a second, since afterwards, in the background, audio is downloaded using a daemon, and mp3 tags are applied.

**Alternative input options**

* Call the function straight from CLI: `main.py https://www.youtube.com/watch?v=NgE5mEQiizQ`
* Provide playlists: `main.py https://www.youtube.com/playlist?v=NgE5mEQiizQ`
* Provide multiple URLs, separated by spaces



## Supported platforms

Currently only YouTube, but I'll add SoundCloud soon.

## Directory structuring

Directory structure follows the recommendation by Plex Media Server:<sup>[1](https://support.plex.tv/articles/205568377-adding-local-artist-and-music-videos/)</sup>

```
Music
└───Album Artist
    └───Album Name├
        ├───1 - Track Name.mp3
        └───folder.jpg
```



## Backbone

Starts with `youtube_search_python` to identify the video with the given URL. Then uses `spotipy` to get meta data. After which it uses `yt-dlp` to download audio, and finally `eye3d` for handling mp3 tags. `pytube` is optional to get a list of URLS from a playlist. 

Tested on Linux and Windows.

## Copyright and use
Audio you download using this script can not contain third-party intellectual property (such as copyrighted material) unless you have permission from that party or are otherwise legally entitled to do so (including by way of any available exceptions or limitations to copyright or related rights provided for in European Union law). You are legally responsible for the Content you submit to the Service.     

1. 