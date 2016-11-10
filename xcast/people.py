import csv
from datetime import datetime
import glob
import json
import os
import re
import urllib
from jinja2 import Environment, PackageLoader

def topic2path(tag):
    t = tag.lower()
    t = re.sub(r'í', 'i', t)
    t = re.sub(r'ó', 'o', t)
    t = re.sub(r'ã', 'a', t)
    t = re.sub(r'[\W_]+', '-', t)
    return t

def html2txt(html):
    #text = re.sub(r'<a\s+href="[^"]+">([^<]+)</a>', '$1', html)
    text = re.sub(r'</?[^>]+>', '', html)
    return text

def new_tag(t):
    return {
        'name' : t,
        'events' : [],
        'videos' : [],
        'episodes' : [],
    }

class GenerateSite(object):
    def __init__(self):
        self.now = datetime.now().strftime('%Y-%m-%d')
        self.sitemap = []
        self.people = {}
        self.search = {}

        self.stats = {
            'has_coc' : 0,
            'has_coc_future' : 0,
            'has_a11y' : 0,
            'has_a11y_future' : 0,
            'has_diversity_tickets' : 0,
            'has_diversity_tickets_future' : 0,
        }
 
    def read_series(self):
        self.event_in_series = {}
        with open('data/series.json') as fh:
            self.series = json.load(fh)
        for s in self.series.keys():
            #self.series[s]['events'] = [ path[12:-4] for path in glob.glob("data/events/" + s + "-*.txt") ]
            l = len(s)
            self.series[s]['events'] = [ e for e in self.conferences if e['nickname'][0:l] == s ]
            self.series[s]['events'].sort(key=lambda x: x['start_date'])
            for e in self.series[s]['events']:
                self.event_in_series[ e['nickname'] ] = s

    def read_sources(self):
        with open('data/sources.json', encoding="utf-8") as fh:
            self.sources = json.load(fh)

    def read_people(self):
        path = 'data/people'
        for filename in glob.glob(path + "/*.txt"):
            try:
                this = {}
                nickname = os.path.basename(filename)
                nickname = nickname[0:-4]
                with open(filename, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.rstrip('\n')
                        if re.search(r'\A\s*\Z', line):
                            continue
                        k,v = re.split(r'\s*:\s*', line, maxsplit=1)
                        this[k] = v
                for field in ['twitter', 'github', 'home']:
                    if field not in this:
                        #print("WARN: {} missing for {}".format(field, nickname))
                        pass
                    elif this[field] == '-':
                        this[field] = None
                self.people[nickname] = {
                    'info': this,
                    'episodes' : [],
                    'hosting' : []
                }
            except Exception as e:
                exit("ERROR: {} in file {}".format(e, filename))
    
        return
    
    def read_tags(self):
        self.tags = {}
        with open('data/tags.csv', encoding="utf-8") as fh:
            rd = csv.DictReader(fh, delimiter=';') 
            for row in rd:
                path = topic2path(row['name'])
                self.tags[ path ] = new_tag(row['name'])
        #print(self.tags)
        return
    
    def read_videos(self):
        path = 'data/videos'
        events = os.listdir(path)
        self.videos = []
        for event in events:
            dir_path = os.path.join(path, event)
            for video_file in os.listdir(dir_path):
                video_file_path = os.path.join(dir_path, video_file)
                with open(video_file_path) as fh:
                    video = json.load(fh)
                    video['filename'] = video_file[0:-5]
                    video['event']    = event
                    video['file_date'] = datetime.fromtimestamp( os.path.getctime(video_file_path) )
                    self.videos.append(video)
    
                    if 'tags' in video:
                        tags = []
                        for t in video['tags']:
                            p = topic2path(t)
                            tags.append({
                                'text': t,
                                'link': p,
                            }) 
                            if p not in self.tags:
                                self.tags[p] = new_tag(t)
                            self.tags[p]['videos'].append(video)
                        video['tags'] = tags
        self.stats['videos'] = len(self.videos)
        return
    
    def read_events(self):
        conferences = []
    
        for filename in glob.glob("data/events/*.txt"):
            print("Reading {}".format(filename))
            conf = {}
            try:
                this = {}
                nickname = os.path.basename(filename)
                nickname = nickname[0:-4]
                #print(nickname)
                this['nickname'] = nickname
                this['file_date'] = datetime.fromtimestamp( os.path.getctime(filename) )
                with open(filename, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.rstrip('\n')
                        if re.search(r'\A\s*#', line):
                            continue
                        if re.search(r'\A\s*\Z', line):
                            continue
                        line = re.sub(r'\s+\Z', '', line)
                        k,v = re.split(r'\s*:\s*', line, maxsplit=1)
                        this[k] = v
    
                my_topics = []
                #print(this)
                if this['topics']:
                    for t in re.split(r'\s*,\s*', this['topics']):
                        p = topic2path(t)
                        my_topics.append({
                            'name' : t,
                            'path' : p,
                        })
                        if p not in self.tags:
                            self.tags[p] = new_tag(t)
                        self.tags[p]['events'].append(this)
                this['topics'] = my_topics
    
                this['cfp_class'] = 'cfp_none'
                cfp = this.get('cfp_date', '')
                if cfp != '':
                    if cfp < self.now:
                        this['cfp_class'] = 'cfp_past'
                    else:
                        this['cfp_class'] = 'cfp_future'
    
                if 'city' not in this or not this['city']:
                    exit("City is missing from {}".format(this))
    
                city_name = '{}, {}'.format(this['city'], this['country'])
                city_page = topic2path('{} {}'.format(this['city'], this['country']))
    
                # In some countris we require state:
                if this['country'] in ['Australia', 'Brasil', 'India', 'USA']:
                    if 'state' not in this or not this['state']:
                        exit('State is missing from {}'.format(this))
                    city_name = '{}, {}, {}'.format(this['city'], this['state'], this['country'])
                    city_page = topic2path('{} {} {}'.format(this['city'], this['state'], this['country']))
                this['city_name'] = city_name
                this['city_page'] = city_page
    
                conferences.append(this)
            except Exception as e:
                exit("ERRORa: {} in file {}".format(e, filename))
    
        self.conferences = sorted(conferences, key=lambda x: x['start_date'])

        return
    
    def read_episodes(self):
        self.episodes = []
        for src in self.sources:
            print("Processing source {}".format(src['name']))
            file = 'data/podcasts/' + src['name'] + '.json'
            src['episodes'] = []
            if os.path.exists(file):
                with open(file, encoding="utf-8") as fh:
                    try:
                        new_episodes = json.load(fh)
                        for episode in new_episodes:
                            episode['source'] = src['name']
                            if 'ep' not in episode:
                                #print("WARN ep missing from {} episode {}".format(src['name'], episode['permalink']))
                                pass
                        self.episodes.extend(new_episodes)
                        src['episodes'] = new_episodes
                    except json.decoder.JSONDecodeError as e:
                        exit("ERROR: Could not read in {} {}".format(file, e))
                        src['episodes'] = [] # let the rest of the code work
                        pass
    
        for e in self.episodes:
            #print(e)
            #exit()
            if 'tags' in e:
                tags = []
                for tag in e['tags']:
                    path = topic2path(tag)
                    if path not in tags:
                        tags.append({
                            'text' : tag,
                            'link' : path,
                        })
                    if path not in self.tags:
                        # TODO report tag missing from the tags.csv file
                        self.tags[path] = new_tag(tag)
                    self.tags[path]['episodes'].append(e)
    
                e['tags'] = tags
    
    
    def preprocess_events(self):
        events = {}
        self.countries = {}
        self.cities = {}
        self.stats['total']  = len(self.conferences)
        self.stats['future'] = len(list(filter(lambda x: x['start_date'] >= self.now, self.conferences)))
        self.stats['cfp']    = len(list(filter(lambda x: x.get('cfp_date', '') >= self.now, self.conferences)))

        for e in self.episodes:
            self.search[ e['title'] + ' (ext)' ] = e['permalink']

        for e in self.conferences:
            events[ e['nickname'] ] = e
        for v in self.videos:
            v['twitter_description'] = html2txt(v['description'])
            v['event_name'] = events[ v['event'] ]['name']
            speakers = {}
            for s in v['speakers']:
                if s in self.people:
                    speakers[s] = self.people[s]
                else:
                    print("WARN: Missing people file for '{}'".format(s))
            v['speakers'] = speakers
    
            tweet_video = '{} http://conferences.szabgab.com/v/{}/{}'.format(v['title'], v['event'], v['filename'])
            tw_id = events[ v['event'] ].get('twitter', '')
            if tw_id:
                tweet_video += ' presented @' + tw_id
            #print(v['speakers'])
            #exit()
            if v['speakers']:
                for s in v['speakers']:
                    tw_id = v['speakers'][s]['info'].get('twitter', '')
                    if tw_id:
                        tweet_video += ' by @' + tw_id
            if 'tags' in v:
                for t in v['tags']:
                    if not re.search(r'-', t['link']) and len(t['link']) < 10:
                        tweet_video += ' #' + t['link']
            v['tweet_video'] = urllib.parse.quote(tweet_video)
    
            #print(speakers)
            #exit()
                
        for e in self.episodes:
            if 'guests' in e:
                for g in e['guests'].keys():
                    if g not in self.people:
                        exit("ERROR: '{}' is not in the list of people".format(g))
                    self.people[g]['episodes'].append(e)
            if 'hosts' in e:
                for h in e['hosts'].keys():
                    if h not in self.people:
                        exit("ERROR: '{}' is not in the list of people".format(h))
                    self.people[h]['hosting'].append(e)
   
        ev = {}
        for v in self.videos:
            if v['event'] not in ev:
                ev[ v['event'] ] = []
            ev[ v['event'] ].append(v)
    
        for event in self.conferences:
            if event['nickname'] in ev:
                event['videos'] = ev[ event['nickname'] ]
    
            if not 'country' in event or not event['country']:
                exit('Country is missing from {}'.format(event))
            country_name = event['country']
            country_page = re.sub(r'\s+', '-', country_name.lower())
            event['country_page'] = country_page
            if country_page not in self.countries:
                self.countries[country_page] = {
                    'name' : country_name,
                    'events' : []
                }
            self.countries[country_page]['events'].append(event)
    
            city_page = event['city_page']
            if city_page not in self.cities:
                self.cities[city_page] = {
                    'name' : event['city_name'],
                    'events' : []
                }
            self.cities[city_page]['events'].append(event)
    
            if event.get('diversitytickets'):
                self.stats['has_diversity_tickets'] += 1
                if event['start_date'] >= self.now:
                    self.stats['has_diversity_tickets_future'] += 1
            if event.get('code_of_conduct'):
                self.stats['has_coc'] += 1
                if event['start_date'] >= self.now:
                    self.stats['has_coc_future'] += 1
            if event.get('accessibility'):
                self.stats['has_a11y']
                if event['start_date'] >= self.now:
                    self.stats['has_a11y_future'] += 1
    
            if 'cfp_date' in event and event['cfp_date'] >= self.now:
                tweet_cfp = 'The CfP of {} ends on {} see {} via http://conferences.szabgab.com/'.format(event['name'], event['cfp_date'], event['url'])
                if event['twitter']:
                    tweet_cfp += ' @' + event['twitter']
                for t in event['topics']:
                    tweet_cfp += ' #' + t['name']
                event['tweet_cfp'] = urllib.parse.quote(tweet_cfp)
    
            tweet_me = event['name']
            tweet_me += ' on ' + event['start_date']
            tweet_me += ' in ' + event['city']
            if 'state' in event:
                tweet_me += ', ' + event['state']
            tweet_me += ' ' + event['country']
            if event['twitter']:
                tweet_me += ' @' + event['twitter']
            tweet_me += " " + event['url']
            for t in event['topics']:
                tweet_me += ' #' + t['name']
            #tweet_me += ' via @szabgab'
            tweet_me += ' via http://conferences.szabgab.com/'
    
            event['tweet_me'] = urllib.parse.quote(tweet_me)
    
        self.stats['coc_future_perc']  = int(100 * self.stats['has_coc_future'] / self.stats['future'])
        self.stats['diversity_tickets_future_perc']  = int(100 * self.stats['has_diversity_tickets_future'] / self.stats['future'])
        self.stats['a11y_future_perc'] = int(100 * self.stats['has_a11y_future'] / self.stats['future'])
    
        return

    def generate_podcast_pages(self):
        env = Environment(loader=PackageLoader('conf', 'templates'))
    
    
        person_template = env.get_template('person.html')
        if not os.path.exists('html/p/'):
            os.mkdir('html/p/')
        for p in self.people.keys():
            self.people[p]['episodes'].sort(key=lambda x : x['date'], reverse=True)
            self.people[p]['hosting'].sort(key=lambda x : x['date'], reverse=True)
            if 'name' not in self.people[p]['info']:
                exit("ERROR: file {} does not have a 'name' field".format(p))
            name = self.people[p]['info']['name']
            path = '/p/' + p
            self.search[name] = path
    
            with open('html' + path, 'w', encoding="utf-8") as fh:
                fh.write(person_template.render(
                    id     = p,
                    person = self.people[p],
                    h1     = self.people[p]['info']['name'],
                    title  = 'Podcasts of and interviews with {}'.format(self.people[p]['info']['name']),
                ))
    
        source_template = env.get_template('podcast.html')
        if not os.path.exists('html/s/'):
            os.mkdir('html/s/')
        for s in self.sources:
            self.search[ s['title'] ] = '/s/' + s['name'];
            try:
                with open('html/s/' + s['name'], 'w', encoding="utf-8") as fh:
                    fh.write(source_template.render(
                        podcast = s,
                        h1     = s['title'],
                        title  = s['title'],
                    ))
            except Exception as e:
                print("ERROR: {}".format(e))
                
    
        tag_template = env.get_template('tag.html')
        if not os.path.exists('html/t/'):
            os.mkdir('html/t/')
    
        self.stats['podcasts'] = len(self.sources)
        self.stats['people']   = len(self.people)
        self.stats['episodes'] = sum(len(x['episodes']) for x in self.sources)
    
        with open('html/people', 'w', encoding="utf-8") as fh:
            fh.write(env.get_template('people.html').render(
                h1      = 'List of people',
                title   = 'List of people',
                stats   = self.stats,
                tags    = self.tags,
                people = self.people,
                people_ids = sorted(self.people.keys()),
            ))
        with open('html/podcasts', 'w', encoding="utf-8") as fh:
            fh.write(env.get_template('podcasts.html').render(
                h1      = 'List of podcasts',
                title   = 'List of podcasts',
                stats   = self.stats,
                tags    = self.tags,
                podcasts = sorted(self.sources, key=lambda x: x['title']),
                people = self.people,
                people_ids = sorted(self.people.keys()),
             ))

    def save_search(self):
        with open('html/search.json', 'w', encoding="utf-8") as fh:
            json.dump(self.search, fh)
    
        return

    def generate_pages(self):
        root = 'html'
        env = Environment(loader=PackageLoader('conf', 'templates'))
    
        self.generate_video_pages()
        #print(self.videos)
        #exit()

        with open(root + '/series', 'w', encoding="utf-8") as fh:
            fh.write(env.get_template('series.html').render(
                h1     = 'Event Series',
                title  = 'Event Series',
                series = self.series,
        ))
        self.sitemap.append({
            'url' : '/series',
        })
 
        with open(root + '/videos', 'w', encoding="utf-8") as fh:
            fh.write(env.get_template('videos.html').render(
                h1     = 'Videos',
                title  = 'Videos',
                videos = self.videos,
        ))
        self.sitemap.append({
            'url' : '/videos',
        })
    
    
        event_template = env.get_template('event.html')
        if not os.path.exists(root + '/e/'):
            os.mkdir(root + '/e/')
        for event in self.conferences:
            #print(event['nickname'])
    
            try:
                with open(root + '/e/' + event['nickname'], 'w', encoding="utf-8") as fh:
                    fh.write(event_template.render(
                        h1          = event['name'],
                        title       = event['name'],
                        event = event,
                ))
                self.sitemap.append({
                    'url' : '/e/' + event['nickname'],
                    'lastmod' : event['file_date'],
                })
            except Exception as e:
                print("ERROR: {}".format(e))
            
    
        future = list(filter(lambda x: x['start_date'] >= self.now, self.conferences))
        #print(future)
        main_template = env.get_template('index.html')
        with open(root + '/index.html', 'w', encoding="utf-8") as fh:
            fh.write(main_template.render(
                h1          = 'Open Source conferences',
                title       = 'Open Source conferences',
                conferences = future,
                stats       = self.stats,
            ))
        self.sitemap.append({
            'url' : '/'
        })
    
        about_template = env.get_template('about.html')
        with open(root + '/about', 'w', encoding="utf-8") as fh:
            fh.write(about_template.render(
                h1          = 'About Open Source conferences',
                title       = 'About Open Source conferences',
            ))
        self.sitemap.append({ 'url' : '/about' })
    
    
        with open(root + '/conferences', 'w', encoding="utf-8") as fh:
            fh.write(main_template.render(
                h1          = 'Tech related conferences',
                title       = 'Tech related conferences',
                conferences = self.conferences,
            ))
        self.sitemap.append({
            'url' : '/conferences'
        })
    
        cfp = list(filter(lambda x: 'cfp_date' in x and x['cfp_date'] >= self.now, self.conferences))
        cfp.sort(key=lambda x: x['cfp_date'])
        #cfp_template = env.get_template('cfp.html')
        with open(root + '/cfp', 'w', encoding="utf-8") as fh:
            fh.write(main_template.render(
                h1          = 'Call for Papers',
                title       = 'Call of Papers',
                conferences = cfp,
            ))
        self.sitemap.append({
            'url' : '/cfp'
        })
    
        with open(root + '/404.html', 'w', encoding="utf-8") as fh:
            template = env.get_template('404.html')
            fh.write(template.render(
                h1          = '404',
                title       = 'Four Oh Four',
            ))
    
        no_code = list(filter(lambda x: not x.get('code_of_conduct'), self.conferences))
        code_template = env.get_template('code-of-conduct.html')
        with open(root + '/code-of-conduct', 'w', encoding="utf-8") as fh:
            fh.write(code_template.render(
                h1          = 'Code of Conduct',
                title       = 'Code of Conduct (or lack of it)',
                conferences = list(filter(lambda x: x['start_date'] >= self.now, no_code)),
                earlier_conferences = list(filter(lambda x: x['start_date'] < self.now, no_code)),
                stats       = self.stats,
    
            ))
        self.sitemap.append({
            'url' : '/code-of-conduct'
        })
    
        diversity_tickets = list(filter(lambda x: x.get('diversitytickets'), self.conferences))
        dt_template = env.get_template('diversity-tickets.html')
        with open(root + '/diversity-tickets', 'w', encoding="utf-8") as fh:
            fh.write(dt_template.render(
                h1          = 'Diversity Tickets',
                title       = 'Diversity Tickets',
                conferences = list(filter(lambda x: x['start_date'] >= self.now, diversity_tickets)),
                earlier_conferences = list(filter(lambda x: x['start_date'] < self.now, diversity_tickets)),
                stats       = self.stats,
            ))
        self.sitemap.append({
            'url' : '/diversity-tickets'
        })
    
    
        #print(topics)
        self.save_pages(root, 't', self.tags, main_template, 'Open source conferences discussing {}')
        self.save_pages(root, 'l', self.countries, main_template, 'Open source conferences in {}')
        self.save_pages(root, 'l', self.cities, main_template, 'Open source conferences in {}')
    
        collections_template = env.get_template('topics.html')
        self.save_collections(root, 't', 'topics', 'Topics', self.tags, collections_template)
        self.save_collections(root, 'l', 'countries', 'Countries', self.countries, collections_template)
        self.save_collections(root, 'l', 'cities', 'Cities', self.cities, collections_template)
    
        with open(root + '/sitemap.xml', 'w', encoding="utf-8") as fh:
            fh.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
            for e in self.sitemap:
                fh.write('  <url>\n')
                fh.write('    <loc>http://conferences.szabgab.com{}</loc>\n'.format(e['url']))
                date = self.now
                if 'lastmod' in e:
                    date = e['lastmod']
                fh.write('    <lastmod>{}</lastmod>\n'.format(date))
                fh.write('  </url>\n')
            fh.write('</urlset>\n')

    def save_collections(self, root, directory, filename, title, data, template):
        for d in data.keys():
            data[d]['future'] = len(list(filter(lambda x: x['start_date'] >= self.now, data[d]['events'])))
            data[d]['total'] =  len(data[d]['events'])
        with open(root + '/' + filename, 'w', encoding="utf-8") as fh:
            fh.write(template.render(
                h1          = title,
                title       = title,
                data        = data,
                directory   = directory,
                stats       = self.stats,
                videos      = (directory == 't'),
                episodes    = (directory == 't'),
            ))
        self.sitemap.append({
            'url' : '/' + filename
        })

    def save_pages(self, root, directory, data, main_template, title):
        my_dir =  root + '/' + directory + '/'
        if not os.path.exists(my_dir):
            os.mkdir(my_dir)
    
        for d in data.keys():
            #print(data[d])
            #exit()
            conferences = sorted(data[d]['events'], key=lambda x: x['start_date'])
            #print("'{}'".format(d))
            #print(my_dir + d)
            with open(my_dir + d, 'w', encoding="utf-8") as fh:
                fh.write(main_template.render(
                    h1          = title.format(data[d]['name']),
                    title       = title.format(data[d]['name']),
                    conferences = list(filter(lambda x: x['start_date'] >= self.now, conferences)),
                    earlier_conferences = list(filter(lambda x: x['start_date'] < self.now, conferences)),
                    videos      = data[d].get('videos'),
                    episodes    = data[d].get('episodes'),
                ))
            self.sitemap.append({
                'url' : '/' + directory + '/' + d
            })

    def generate_video_pages(self):
        root = 'html'
        env = Environment(loader=PackageLoader('conf', 'templates'))
        video_template = env.get_template('video.html')
        if not os.path.exists(root + '/v/'):
            os.mkdir(root + '/v/')
        for video in self.videos:
            if not os.path.exists(root + '/v/' + video['event']):
                os.mkdir(root + '/v/' + video['event'])
            #print(root + '/v/' + video['event'] + '/' + video['filename'])
            #exit()
            with open(root + '/v/' + video['event'] + '/' + video['filename'], 'w', encoding="utf-8") as fh:
                fh.write(video_template.render(
                    h1          = video['title'],
                    title       = video['title'],
                    video       = video,
                ))
            self.sitemap.append({
                'url' : '/v/' + video['event'] + video['filename'],
                'lastmod' : video['file_date'],
            })
     


# vim: expandtab
