"""Bounded public-source GET recovery; no live network or model calls."""
import contextlib
import io
import json
import unittest
import urllib.error
from email.message import Message
from http.client import IncompleteRead
from unittest.mock import patch
import update_daily as u

URL="https://export.arxiv.org/api/query?id_list=2611.12345&private=not-for-logs"

class Response:
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self):return b"successful public response"

def http_error(code,retry_after=None):
 headers=Message()
 if retry_after is not None:headers["Retry-After"]=retry_after
 return urllib.error.HTTPError(URL,code,"temporary source error",headers,None)

class FetchTests(unittest.TestCase):
 def fetch(self,effects):
  stream=io.StringIO()
  with patch.object(u.urllib.request,"urlopen",side_effect=effects) as request,patch.object(u.time,"sleep") as sleep,contextlib.redirect_stdout(stream):
   result=u.fetch(URL)
  return result,request,sleep,stream.getvalue()
 def test_transient_failure_recovers_without_changing_request_or_timeout(self):
  result,request,sleep,log=self.fetch([urllib.error.URLError("temporary DNS failure"),Response()])
  self.assertEqual(result,"successful public response")
  sleep.assert_called_once_with(3)
  self.assertEqual(request.call_count,2)
  for call in request.call_args_list:
   req=call.args[0]
   self.assertEqual(req.full_url,URL)
   self.assertEqual(req.get_method(),"GET")
   self.assertEqual(call.kwargs["timeout"],55)
   self.assertEqual(req.get_header("Cache-control"),"no-cache")
  self.assertIn("export.arxiv.org/api/query",log)
  self.assertNotIn("private=",log)
  self.assertNotIn("2611.12345",log)
 def test_transient_exhaustion_still_raises_after_three_requests(self):
  failure=urllib.error.URLError("DNS unavailable")
  with patch.object(u.urllib.request,"urlopen",side_effect=failure) as request,patch.object(u.time,"sleep") as sleep,contextlib.redirect_stdout(io.StringIO()),self.assertRaises(urllib.error.URLError):
   u.fetch(URL)
  self.assertEqual(request.call_count,3)
  self.assertEqual([call.args[0] for call in sleep.call_args_list],[3,6])
 def test_permanent_403_and_404_are_not_retried(self):
  for code in (400,401,403,404):
   with self.subTest(code=code),patch.object(u.urllib.request,"urlopen",side_effect=http_error(code)) as request,patch.object(u.time,"sleep") as sleep,self.assertRaises(urllib.error.HTTPError):
    u.fetch(URL)
   self.assertEqual(request.call_count,1)
   sleep.assert_not_called()
 def test_retryable_http_statuses_are_retried(self):
  for code in (429,500,502,503,504):
   with self.subTest(code=code):
    result,request,sleep,_=self.fetch([http_error(code),Response()])
    self.assertEqual(result,"successful public response")
    self.assertEqual(request.call_count,2)
    sleep.assert_called_once_with(3)
 def test_retry_after_is_capped_instead_of_waiting_indefinitely(self):
  _,_,sleep,_=self.fetch([http_error(429,"999999"),Response()])
  sleep.assert_called_once_with(30)
 def test_bad_retry_after_uses_bounded_backoff(self):
  _,_,sleep,_=self.fetch([http_error(503,"not-a-date"),Response()])
  sleep.assert_called_once_with(3)
 def test_incomplete_reads_and_timeouts_recover(self):
  _,request,sleep,_=self.fetch([IncompleteRead(b"partial",100),TimeoutError("timeout"),Response()])
  self.assertEqual(request.call_count,3)
  self.assertEqual([call.args[0] for call in sleep.call_args_list],[3,6])
 def test_value_error_is_not_treated_as_transient_network_failure(self):
  with patch.object(u.urllib.request,"urlopen",side_effect=ValueError("invalid date evidence")) as request,patch.object(u.time,"sleep") as sleep,self.assertRaisesRegex(ValueError,"invalid date"):
   u.fetch(URL)
  self.assertEqual(request.call_count,1)
  sleep.assert_not_called()
 def test_crossref_does_not_multiply_network_retry_attempts(self):
  with patch.object(u.urllib.request,"urlopen",side_effect=http_error(503)) as request,patch.object(u.time,"sleep") as sleep,contextlib.redirect_stdout(io.StringIO()),self.assertRaises(urllib.error.HTTPError):
   list(u.crossref_records("0031-9007","2026-11-11","2026-11-11"))
  self.assertEqual(request.call_count,3)
  self.assertEqual(len(sleep.call_args_list),2)
 def test_source_failure_names_source_and_error_without_query_values(self):
  error=urllib.error.URLError("cannot connect to "+URL)
  stream=io.StringIO()
  with contextlib.redirect_stdout(stream):details=u.source_failure("arXiv",error)
  self.assertEqual(details["status"],"failed")
  self.assertEqual(details["error_type"],"URLError")
  self.assertIn("arXiv",stream.getvalue())
  self.assertIn("export.arxiv.org/api/query",stream.getvalue())
  self.assertNotIn("private=",stream.getvalue())
  self.assertNotIn("2611.12345",json.dumps(details))

if __name__=="__main__":unittest.main()