from initialize import music_dir, spotify_api, Path
from utils import json_out, json_in
from tag_manager import timeout_handler
import eyed3
from time import sleep
from datetime import datetime

ps = 40
err_max = 0.3

all_files_path = Path('all_files.json')
faulty_path = Path('duration_violations.json')
all_errs_path = Path('all_errs.json')

if not all_files_path.is_file():
    json_out({}, all_files_path)
    json_out({}, faulty_path)
    json_out([], all_errs_path)
all_files = json_in(all_files_path)
faulty = json_in(faulty_path)
all_errs = json_in(all_errs_path)
#########
n_songs = 13901
i = 0
attempts = 0
while i < n_songs - 1:
    attempts += 1
    print('Starting attempt number', attempts)
    try:
        for i, file_path in enumerate(music_dir.glob('*/*/*.mp3')):
            if str(file_path) in all_files:
                print(f'{datetime.now():%H:%M} {str(i).rjust(5)}/{n_songs}', f'({i/n_songs:.0%})'.rjust(6), file_path)
                continue
            file = eyed3.load(file_path)
            tags = file.tag
            uri = None
            if hasattr(tags, 'internet_radio_url'):
                t_real = file.info.time_secs
                # get song by uri
                uri = tags.internet_radio_url
                if uri is None:
                    all_files[str(file_path)] = uri
                    continue
                elif 'youtu' in uri or 'manual' in uri:
                    all_files[str(file_path)] = uri
                    continue
                meta = timeout_handler(func=spotify_api.track, track_id=uri)
                t_desired = meta['duration_ms'] / 1000
                if t_desired == 0:  # yes this happens
                    t_desired = 1
                all_errs.append(t_real / t_desired)
                t_err = abs(t_real / t_desired - 1)
                print(
                    f'{datetime.now():%H:%M}',
                    str(i).rjust(5), f'({i/13749:.0%})'.rjust(6),
                    tags.album_artist[:ps].ljust(ps),
                    tags.title[:ps].ljust(ps),
                    f'{t_err:.1%}',
                )
                if t_err > err_max:
                    faulty[uri] = (t_desired, t_real, t_err)
            all_files[str(file_path)] = uri
        print('Finished collecting tracks at fault')
    except Exception as e:
        print('Broke during collecting tracks at fault:\n', e)
        breakpoint()
        pass
    # json_out(faulty, 'duration_violations.json')
    # json_out(all_errs, 'all_errs.json')
    # json_out(all_files, 'all_files.json')
    sleep(60)
####



# from matplotlib import pyplot as plt
import numpy as np
from matplotlib import pyplot as plt

plt.hist(all_errs, np.linspace(0, 10, 50))
plt.ylim(0, 300)
plt.show()