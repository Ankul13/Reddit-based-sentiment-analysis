"""
Management command to manually upload results to HDFS and create Hive table.
Run from reddit_intelligence/ folder:

    python manage.py load_to_hive
    python manage.py load_to_hive --product "Samsung Galaxy S25"
"""
import os
import glob
import subprocess
import shutil
from django.core.management.base import BaseCommand


NOISE = ('SLF4J', 'log4j', 'WARN', 'INFO', 'Hive Session', 'OK', 'Time taken')

HQL = (
    "CREATE DATABASE IF NOT EXISTS reddit_analysis; "
    "USE reddit_analysis; "
    "DROP TABLE IF EXISTS reddit_results; "
    "CREATE EXTERNAL TABLE reddit_results ("
    "id STRING, title STRING, text STRING, cleaned_text STRING, "
    "subreddit STRING, score INT, comments INT, created_utc DOUBLE, "
    "sentiment STRING, sentiment_score DOUBLE, "
    "emotion STRING, emotion_score DOUBLE"
    ") ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' "
    "STORED AS TEXTFILE "
    "LOCATION '/reddit_data/results' "
    "TBLPROPERTIES ('skip.header.line.count'='1');"
)


class Command(BaseCommand):
    help = 'Upload analysis results to HDFS and create Hive external table'

    def add_arguments(self, parser):
        parser.add_argument(
            '--product', type=str, default=None,
            help='Product name to upload (default: all results)'
        )

    def handle(self, *args, **options):
        product = options.get('product')

        # Check hadoop
        if not shutil.which('hadoop'):
            self.stdout.write(self.style.ERROR(
                'hadoop not found on PATH.\n'
                'Start Hadoop first: start-all.sh\n'
                'Then run this command again.'
            ))
            return

        # Find result files
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )))
        results_dir = os.path.join(base_dir, 'data', 'results')

        if product:
            safe = product.replace(' ', '_')
            files = glob.glob(os.path.join(results_dir, f'{safe}_analysis.csv'))
        else:
            files = glob.glob(os.path.join(results_dir, '*_analysis.csv'))

        if not files:
            self.stdout.write(self.style.WARNING(
                f'No result CSV files found in {results_dir}\n'
                'Run an analysis first from the dashboard.'
            ))
            return

        self.stdout.write(f'Found {len(files)} result file(s).')

        # Step 1 - Create HDFS dirs
        self.stdout.write('Creating HDFS directories...')
        for hdfs_dir in ['/reddit_data/raw', '/reddit_data/clean', '/reddit_data/results']:
            subprocess.run(['hadoop', 'fs', '-mkdir', '-p', hdfs_dir],
                           capture_output=True, timeout=30)
        self.stdout.write(self.style.SUCCESS('  HDFS directories ready'))

        # Step 2 - Upload each result file
        for fpath in files:
            fname = os.path.basename(fpath)
            self.stdout.write(f'  Uploading {fname}...')
            r = subprocess.run(
                ['hadoop', 'fs', '-put', '-f', fpath, '/reddit_data/results/'],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode == 0:
                self.stdout.write(self.style.SUCCESS(f'    Uploaded {fname}'))
            else:
                self.stdout.write(self.style.ERROR(f'    Failed: {r.stderr[:200]}'))

        # Also upload raw and clean if they exist
        for subdir in ['raw', 'clean']:
            local_dir = os.path.join(base_dir, 'data', subdir)
            hdfs_dir  = f'/reddit_data/{subdir}'
            for csv in glob.glob(os.path.join(local_dir, '*.csv')):
                subprocess.run(['hadoop', 'fs', '-put', '-f', csv, hdfs_dir + '/'],
                               capture_output=True, timeout=60)

        # Step 3 - Create Hive table
        if not shutil.which('hive'):
            self.stdout.write(self.style.WARNING(
                'hive not found on PATH.\n'
                'Start Hive metastore: hive --service metastore &\n'
                'Then run: hive -f hive_queries.sql'
            ))
            return

        self.stdout.write('Creating Hive external table...')
        result = subprocess.run(
            ['hive', '-e', HQL],
            capture_output=True, text=True, timeout=300
        )

        if result.returncode == 0:
            self.stdout.write(self.style.SUCCESS(
                'Hive table "reddit_results" created successfully!\n'
                'Go to http://127.0.0.1:8000/hive/ to run queries.'
            ))
            # Verify row count
            count_result = subprocess.run(
                ['hive', '-e', 'USE reddit_analysis; SELECT COUNT(*) FROM reddit_results;'],
                capture_output=True, text=True, timeout=120
            )
            clean_out = '\n'.join(
                l for l in count_result.stdout.split('\n')
                if l.strip() and not any(n in l for n in NOISE)
            )
            if clean_out.strip():
                self.stdout.write(f'  Row count: {clean_out.strip()}')
        else:
            real_err = '\n'.join(
                l for l in result.stderr.split('\n')
                if l.strip() and not any(n in l for n in NOISE)
            )
            if real_err:
                self.stdout.write(self.style.ERROR(f'Hive error:\n{real_err[:400]}'))
            else:
                self.stdout.write(self.style.SUCCESS('Hive table step completed.'))