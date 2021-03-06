import os
import re

import requests
from requests_html import HTMLSession
from slugify import slugify
from tqdm import tqdm


class ArdMediathekDownloader(object):
    """
    Commandline python script tool to download videos from the online ARD mediathek
    """

    def __init__(self, url):
        """
        Constructor.
        The URL will be checked already here.
        """
        self.url = self.validate_url(url)
        self.subtitle_url = None
        self._filename = None
        self.default_filename = "video.mp4"
        self._derive_filename = False
        self._quality = 3

    def validate_url(self, url):
        """
        Method to check if the URL is a valid URL or not.

        Returns the URL if everything is fine with it otherwise rises a ValueError.
        """
        regex = re.compile(
            r'^(?:http)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        try:
            return re.match(regex, url).group(0)
        except:
            raise ValueError("The given URL is not valid.")

    def download(self):
        """
        Downloads the video into its destination path.
        """
        self._determine_filename()

        video_url = self.get_video_url()

        self.download_by_video_url(video_url)

    def _determine_filename(self):
        if self.filename is None:  # no filename was given - override it with default value
            fn = self.default_filename
            if self.derive_filename:
                fn = self._get_filename_from_url(self.url)

            self.filename = os.path.join(os.getcwd(), fn)
            print(f"Since no filename was given the default value '{os.path.basename(self.filename)}' will be used.")

    def download_by_video_url(self, video_url):
        # request and store video_url
        r = requests.get(video_url, stream=True)
        chunk_size = 4096
        with open(self.filename, 'wb') as fd:
            filesize = int(r.headers['content-length'])
            print(f"Downloading destination:{self.filename}")
            with tqdm(total=filesize, desc="Downloading", unit="byte", unit_scale=True, unit_divisor=1024) as bar:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    bar.update(chunk_size)
                    fd.write(chunk)

    def get_video_url(self):
        # get documentId from HTML
        doc_id_result = re.search(r'documentId=(\d+)', self.url)
        if doc_id_result is None:
            raise RuntimeError("The document id could not be found.")
        doc_id = doc_id_result.group(1)
        json = self._get_media_json_by_document_id(doc_id)
        # get subtitle URL from JSON
        if '_subtitleUrl' in json:
            self.subtitle_url = json['_subtitleUrl']
        video_url = self._get_video_url(json)
        return video_url

    def _get_media_json_by_document_id(self, doc_id):
        # request json file from Mediathek
        r = requests.get(f"http://www.ardmediathek.de/play/media/{doc_id}?devicetype=pc&features")
        if not 'application/json' in r.headers.get('content-type'):
            raise RuntimeError("The server didn't reply with JSON which indicates that an error occured.")
        json = r.json()
        return json

    def _get_video_url(self, json):
        # if video is available in the desired quality, get that url, else get the best available
        media = json['_mediaArray']
        return self._get_video_by_quality(media)

    def _get_video_by_quality(self, media):
        medias = self._get_all_stream_urls_grouped_by_quality(media)
        if self.quality in medias:
            url = medias[self.quality]
            url = self.fix_url(url)

            return url
        else:
            raise RuntimeError(f"Cannot find a video for quality. Available Qualities are:{medias.keys()}")

    def _get_all_stream_urls_grouped_by_quality(self, medias):
        videos_by_size = {}
        for medium in medias:
            streams = medium['_mediaStreamArray']
            for stream in streams:
                stream_url_or_list_of_urls = stream['_stream']
                if "," in stream_url_or_list_of_urls:
                    continue

                if type(stream_url_or_list_of_urls) == str:
                    s = self.get_size_of_video(stream_url_or_list_of_urls)
                    videos_by_size[s] = stream_url_or_list_of_urls
                else:
                    for stream_url in stream_url_or_list_of_urls:
                        if "," in stream_url:
                            continue
                        s = self.get_size_of_video(stream_url)
                        videos_by_size[s] = stream_url

        keys = sorted(k for k in videos_by_size.keys() if k > 0)

        if len(keys) > 3:
            keys = keys[-3:]

        result = {1: videos_by_size.get(keys[0]),
                  2: videos_by_size.get(keys[len(keys) // 2]),
                  3: videos_by_size.get(keys[-1])}

        return result

    def get_size_of_video(self, url):
        url = self.fix_url(url)
        r = requests.head(url)
        h = r.headers
        return int(h.get("Content-Length"))

    def fix_url(self, url):
        if not url.startswith('http:') and not url.startswith('https:'):
            url = "http:" + url
        return url

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, filename):
        """
        Checks and sets the filename where the filename consists of the path *and* the filename.
        If the path does not exist yet, this method will try to build it.

        Returns the filename or None.
        """
        if not filename:
            return None

        self._filename = os.path.abspath(os.path.expanduser(filename))
        return self._filename

    @property
    def quality(self):
        return self._quality

    @quality.setter
    def quality(self, quality):
        """
        Set the desired video quality
        """
        self._quality = quality

    @property
    def derive_filename(self):
        return self._derive_filename

    @derive_filename.setter
    def derive_filename(self, derive_filename):
        """
        Should the filename be derived from the content of the ARD mediathek web page?
        :param derive_filename:
        :return:
        """
        self._derive_filename = derive_filename

    def get_subtitles(self):

        """
        download subtitles in srt format
        """

        if not self.subtitle_url:
            raise RuntimeError("Video does not contain subtitles")

        ut_file = requests.get(self.subtitle_url).text
        with open(os.path.splitext(self.filename)[0 ] +'.srt' ,'w') as f:
            f.write(ut_file)
        print(f"subtitles saved as {(os.path.splitext(os.path.basename(self.filename))[0]+'.srt')}")

        # subtitles are in Timed Text Authoring Format V1.0 (DFXP http://www.w3.org/2006/10/ttaf1)
        # ut = pycaption.DFXPReader().read(ut_file)
        # for some reason there is a 10 hour offset on the subtitle timestamp (= 10*60*60*1000000 us)
        # ut.adjust_caption_timing(offset=-10*60*60*1000000)

        # if self.filename is None: # no filename was given - override it with default value
        #    self.filename = os.path.join(os.getcwd(), self.default_filename)
        #
        # with open(os.path.splitext(self.filename)[0]+'.srt', 'wb') as f:
        #    f.write(pycaption.SRTWriter().write(ut))
        # print(f"subtitles saved as {(os.path.splitext(os.path.basename(self.filename))[0]+'.srt')}")

    def _get_filename_from_url(self, url):
        html_session = HTMLSession()
        response = html_session.get(self.url)
        title = response.html.find('title', first=True).text
        return slugify(title.partition("|")[0].strip()) + ".mp4"
