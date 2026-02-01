# things to fix
- fix fixup_ocr.py for many of these case where most of page is in footnotes:
    Processing page388_image1...
    Loaded 1126 OCR words
    Metadata: page=300, book=GENESIS
    Excluded 4 header words: ['300', 'GENESIS.', 'CH.', 'V.']
    Markdown: 1075 body words, 34 footnote words
    Fixed 24 spelling errors (2.1%)
    Moved 632 words to footnotes (56.1%)
- fix bounding boxes:
    - should not straddle columns
    - should always extend from edge to margin or vice versa
- add webhooks for clerk to manage users
- add user preferences
- add running list of prompt/answers in UI
- keep track of user prompt history/answers


# things done
- fix ingestion issue with introductions
- gen 1:1
- add hog lib for analytics
- add langfuse
- add user feedback/report issue feature
- deal with privacy notices
- add verse references to prompt
- diagnose references missing from answers and why these are said to be Verified
