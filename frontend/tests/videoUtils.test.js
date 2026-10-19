import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  extractYouTubeVideoId,
  getYouTubeEmbedUrl,
  ALLOWED_YOUTUBE_HOSTS
} from '../src/utils/videoUtils.js';

describe('Video Recommendation Player URL Security Tests', () => {
  test('extracts valid 11-character video ID from standard watch URL', () => {
    const id = extractYouTubeVideoId('https://www.youtube.com/watch?v=IPvYjXCsTg8');
    assert.equal(id, 'IPvYjXCsTg8');
  });

  test('extracts valid 11-character video ID with query parameters and timestamps', () => {
    const id = extractYouTubeVideoId('https://www.youtube.com/watch?v=IPvYjXCsTg8&t=120s&list=xyz');
    assert.equal(id, 'IPvYjXCsTg8');
  });

  test('extracts valid 11-character video ID from youtu.be short URL', () => {
    const id = extractYouTubeVideoId('https://youtu.be/IPvYjXCsTg8');
    assert.equal(id, 'IPvYjXCsTg8');
  });

  test('extracts valid 11-character video ID from embed and nocookie URLs', () => {
    assert.equal(extractYouTubeVideoId('https://www.youtube.com/embed/IPvYjXCsTg8'), 'IPvYjXCsTg8');
    assert.equal(extractYouTubeVideoId('https://www.youtube-nocookie.com/embed/IPvYjXCsTg8'), 'IPvYjXCsTg8');
  });

  test('extracts valid 11-character video ID from shorts URL', () => {
    assert.equal(extractYouTubeVideoId('https://www.youtube.com/shorts/IPvYjXCsTg8'), 'IPvYjXCsTg8');
  });

  test('accepts raw 11-character alphanumeric video ID', () => {
    assert.equal(extractYouTubeVideoId('IPvYjXCsTg8'), 'IPvYjXCsTg8');
    assert.equal(extractYouTubeVideoId('8hly31xKli0'), '8hly31xKli0');
  });

  test('rejects deceptive domains and lookalike hostnames', () => {
    assert.equal(extractYouTubeVideoId('https://youtube.com.attacker.com/watch?v=IPvYjXCsTg8'), null);
    assert.equal(extractYouTubeVideoId('https://evil-youtube.com/watch?v=IPvYjXCsTg8'), null);
    assert.equal(extractYouTubeVideoId('https://fakeyoutu.be/IPvYjXCsTg8'), null);
  });

  test('rejects URLs with embedded userinfo / credentials', () => {
    assert.equal(extractYouTubeVideoId('https://user:password@www.youtube.com/watch?v=IPvYjXCsTg8'), null);
  });

  test('rejects URLs with unexpected ports', () => {
    assert.equal(extractYouTubeVideoId('https://www.youtube.com:8080/watch?v=IPvYjXCsTg8'), null);
    assert.equal(extractYouTubeVideoId('https://www.youtube.com:4444/watch?v=IPvYjXCsTg8'), null);
  });

  test('rejects malicious injection strings and non-http protocols', () => {
    assert.equal(extractYouTubeVideoId('javascript:alert(1)'), null);
    assert.equal(extractYouTubeVideoId('data:text/html,<script>alert(1)</script>'), null);
    assert.equal(extractYouTubeVideoId('ftp://www.youtube.com/watch?v=IPvYjXCsTg8'), null);
    assert.equal(extractYouTubeVideoId('<script>alert("xss")</script>'), null);
    assert.equal(extractYouTubeVideoId('https://www.youtube.com/watch?v=toolongvideoid12345'), null);
    assert.equal(extractYouTubeVideoId('https://www.youtube.com/watch?v=tooshort'), null);
  });

  test('handles null, undefined, empty, and non-string inputs safely', () => {
    assert.equal(extractYouTubeVideoId(null), null);
    assert.equal(extractYouTubeVideoId(undefined), null);
    assert.equal(extractYouTubeVideoId(''), null);
    assert.equal(extractYouTubeVideoId('   '), null);
    assert.equal(extractYouTubeVideoId(12345), null);
    assert.equal(extractYouTubeVideoId({}), null);
  });

  test('builds privacy-enhanced sandbox-safe embed URLs using youtube-nocookie.com', () => {
    const embedUrl = getYouTubeEmbedUrl('https://www.youtube.com/watch?v=IPvYjXCsTg8&token=secret_123');
    assert.equal(
      embedUrl,
      'https://www.youtube-nocookie.com/embed/IPvYjXCsTg8?rel=0&modestbranding=1&enablejsapi=1'
    );
    assert.ok(!embedUrl.includes('token'));
    assert.ok(!embedUrl.includes('secret_123'));
  });

  test('returns null for embed URL when video input is invalid or missing', () => {
    assert.equal(getYouTubeEmbedUrl(null), null);
    assert.equal(getYouTubeEmbedUrl(''), null);
    assert.equal(getYouTubeEmbedUrl('https://evil.com/video'), null);
  });
});
