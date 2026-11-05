import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generate_drafts.py"
spec = importlib.util.spec_from_file_location("generate_drafts", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ReviewFlagTests(unittest.TestCase):
    def test_content_type_classification(self):
        cases = [
            ('ハローワークプラザ下関が移転', '公共・地域施設'),
            ('徳山有楽町郵便局がリニューアル', '公共・地域施設'),
            ('須金観光農園がオープン', '観光・レジャー'),
            ('東横イン宇部新川駅前が開業', '宿泊施設'),
            ('ケーズデンキ山口店がオープン', '店舗・商業施設'),
            ('サイゼリヤおのだサンパーク店が開店', '店舗・商業施設'),
            ('下関テイラーズ 市民共創の拠点施設がオープン', '公共・地域施設'),
            ('民間の交流拠点施設がオープン', 'その他施設・サービス（要確認）'),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(module.classify_content_type(title), expected)

    def test_civic_co_creation_hubs_are_classified_as_public_and_excluded_from_store_drafts(self):
        item = {
            'url': 'https://example.com/shimonoseki-tailors',
            'title': '市民共創の拠点施設完成「下関テイラーズ」オープン',
            'category': ['新店・開店'],
            'published_date': '2026-09-23',
            'body_excerpt': '市民自らが地域の魅力を発信する常設拠点',
            'source_name': 'test',
        }
        self.assertEqual(module.classify_content_type(item['title'], item['body_excerpt']), '公共・地域施設')
        self.assertIsNone(module.convert_candidate(item, 'RSS', 2))

    def test_preopening_event_announcement_is_not_treated_as_facility_opening(self):
        title = '秋吉台エコ・ミュージアム プレオープンイベントの開催について'
        item = {
            'url': 'https://example.com/akiyoshidai-event',
            'title': title,
            'category': ['新店・開店'],
            'published_date': '2026-11-04',
            'body_excerpt': 'プレオープンイベントの詳細が決定しましたのでお知らせします。',
            'source_name': '山口県公式・報道発表',
        }
        self.assertFalse(module.is_store_news(title, item['body_excerpt']))
        self.assertIsNone(module.convert_candidate(item, 'RSS', 2))

    def test_real_store_opening_with_celebration_event_is_kept(self):
        title = '宇部市にカフェ新店舗オープン記念イベント開催'
        body = 'カフェが11月5日にオープンしました。'
        item = {
            'url': 'https://example.com/cafe-opening',
            'title': title,
            'category': ['新店・開店'],
            'published_date': '2026-11-05',
            'body_excerpt': body,
            'source_name': 'test',
        }
        self.assertTrue(module.is_store_news(title, body))
        self.assertIsNotNone(module.convert_candidate(item, 'RSS', 2))

    def test_facility_preopening_event_is_not_treated_as_new_opening(self):
        title = '秋吉台エコ・ミュージアム プレオープンイベントの開催について'
        body = 'プレオープンイベントについて、詳細が決定しました。多くの方の御来場をお待ちしています。'
        item = {
            'url': 'https://example.com/akiyoshidai-event',
            'title': title,
            'category': ['新店・開店'],
            'published_date': '2026-11-04',
            'body_excerpt': body,
            'source_name': 'test',
        }
        self.assertFalse(module.is_store_news(title, body))
        self.assertIsNone(module.convert_candidate(item, '公式サイト', 1))

    def test_open_campus_is_not_treated_as_store_opening(self):
        title = '山口県立農業大学校「夏のオープンキャンパス」を開催'
        item = {
            'url': 'https://example.com/open-campus',
            'title': title,
            'category': ['新店・開店'],
            'published_date': '2026-11-01',
            'body_excerpt': 'オープンキャンパスを開催します。',
            'source_name': 'test',
        }
        self.assertFalse(module.is_store_news(title, item['body_excerpt']))
        self.assertIsNone(module.convert_candidate(item, 'RSS', 2))

    def test_public_facilities_are_excluded_from_store_drafts(self):
        cases = [
            ('ハローワークプラザ下関が移転', '公共・地域施設', ['移転']),
            ('徳山有楽町郵便局がリニューアル', '公共・地域施設', ['リニューアル']),
            ('山口市立図書館がリニューアル', '公共・地域施設', ['リニューアル']),
        ]
        for title, expected_type, categories in cases:
            with self.subTest(title=title):
                item = {
                    'url': 'https://example.com/post',
                    'title': title,
                    'category': categories,
                    'published_date': '2026-11-01',
                    'body_excerpt': '',
                    'source_name': 'test',
                }
                self.assertEqual(module.classify_content_type(title), expected_type)
                self.assertIsNone(module.convert_candidate(item, 'RSS', 2))

    def test_hotel_and_leisure_candidates_remain_separately_classified(self):
        cases = [
            ('東横イン宇部新川駅前が開業', '宿泊施設'),
            ('須金観光農園がオープン', '観光・レジャー'),
            ('ケーズデンキ山口店がオープン', '店舗・商業施設'),
        ]
        for title, expected_type in cases:
            with self.subTest(title=title):
                item = {
                    'url': 'https://example.com/post',
                    'title': title,
                    'category': ['新店・開店'],
                    'published_date': '2026-11-01',
                    'body_excerpt': '',
                    'source_name': 'test',
                }
                converted = module.convert_candidate(item, 'RSS', 2)
                self.assertIsNotNone(converted)
                self.assertEqual(module.classify_content_type(title), expected_type)

    def test_lodging_classification_uses_facility_name_not_incidental_body_mentions(self):
        cases = [
            ('山口市に新しい民泊施設が開業', '宿泊施設'),
            ('萩市のゲストハウスがリニューアル', '宿泊施設'),
            ('長門市の旅館が営業終了', '宿泊施設'),
            ('山口市のカフェがオープン', '店舗・商業施設'),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(module.classify_content_type(title, '近隣にはホテルや旅館があります。'), expected)

    def test_make_draft_keeps_unverified_status_and_content_type(self):
        item = {'url': 'https://example.com/post', 'title': '東横イン宇部新川駅前が開業',
                'category': ['新店・開店'], 'published_date': '2026-11-01',
                'body_excerpt': 'ホテルが開業', 'source_name': 'test'}
        draft = module.make_draft(item)
        self.assertEqual(draft['content_type'], '宿泊施設')
        self.assertEqual(draft['status'], '未確認・公開禁止')

    def test_similar_titles_flagged_not_removed(self):
        drafts = [
            {"id":"a","title":"【開店】カフェ青空 宇部店","category":["新店・開店"],"source_url":"https://example.com/a","source_urls":[{"url":"https://example.com/a"}],"body_excerpt":"紹介文","published_date":"2026-10-01","municipality":"宇部市","municipality_candidates":["宇部市"],"freshness":"直近30日","status":"x"},
            {"id":"b","title":"2026年10月1日 【開店】カフェ青空 宇部店","category":["新店・開店"],"source_url":"https://example.com/b","source_urls":[{"url":"https://example.com/b"}],"body_excerpt":"別記事","published_date":"2026-10-01","municipality":"宇部市","municipality_candidates":["宇部市"],"freshness":"直近30日","status":"x"},
        ]
        summary = module.annotate_review_flags(drafts)
        self.assertEqual(len(drafts), 2)
        self.assertEqual(summary["duplicate_group_count"], 1)
        self.assertTrue(all(x["duplicate_review"] == "重複の可能性・要確認" for x in drafts))
        self.assertTrue(all(x["status"] == "未確認・公開禁止" for x in drafts))

    def test_missing_data_flagged(self):
        drafts = [{"id":"x","title":"店舗","category":["閉店"],"source_url":"","source_urls":[],"body_excerpt":"","published_date":"","municipality":"","municipality_candidates":[],"freshness":"日付確認が必要","status":"x"}]
        module.annotate_review_flags(drafts)
        self.assertIn("情報源URLなし", drafts[0]["review_flags"])
        self.assertIn("本文抜粋なし", drafts[0]["review_flags"])
        self.assertIn("公開日未確認", drafts[0]["review_flags"])
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")

if __name__ == "__main__":
    unittest.main()
