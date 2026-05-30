from crawler.gcs_uploader import _json_blob_name, _image_blob_name


def test_json_blob_name_is_date_partitioned():
    assert (
        _json_blob_name("2026-05-29", page=1, filename="3.json")
        == "dt=2026-05-29/1/3.json"
    )


def test_image_blob_name_is_date_partitioned():
    assert (
        _image_blob_name("2026-05-29", relative="ABC123/0.jpg")
        == "dt=2026-05-29/images/ABC123/0.jpg"
    )
