from tests.utils import PixJourney


def risk_rejections(results: list) -> list:
    return [result for result in results if result[1] == "rejected" and result[2] != ["ACCOUNT_BLOCKED"]]


class TestDestinationReincidence:
    def test_destination_is_blocked_after_more_than_8_risk_rejections(self):
        first = PixJourney.new()
        PixJourney.send(first)

        results = PixJourney.block_destination(first)
        rejections = risk_rejections(results)

        assert len(rejections) == 9
        assert all(reasons == ["DEST_RECEIVING_VELOCITY"] for _payload, _status, reasons in rejections)
        assert results[-1][2] == ["ACCOUNT_BLOCKED"]

    def test_counting_restarts_after_unblock(self):
        first = PixJourney.new()
        PixJourney.send(first)
        PixJourney.block_destination(first)

        status_code, _response = PixJourney.unblock_destination(first)
        assert status_code == 200

        for _ in range(2):
            status, reasons = PixJourney.send(PixJourney.to_same_destination(first))
            assert (status, reasons) == ("rejected", ["DEST_RECEIVING_VELOCITY"])


class TestSourceReincidence:
    def test_source_is_blocked_after_more_than_10_risk_rejections(self):
        first = PixJourney.new()
        PixJourney.send(first)

        results = PixJourney.block_source(first)
        rejections = risk_rejections(results)

        assert len(rejections) == 11
        assert all(reasons == ["SRC_SENDING_VELOCITY"] for _payload, _status, reasons in rejections)
        assert results[-1][2] == ["ACCOUNT_BLOCKED"]
