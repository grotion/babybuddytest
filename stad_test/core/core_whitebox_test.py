######################################################################################################################
# core whitebox test                                                                                                 #
#                                                                                                                    #
# Author: Shaun Ku, Samson Cournane                                                                                  #
#                                                                                                                    #
#                                                                                                                    #
# Test result                                                                                                        #
# ------------------------------------------------------------------------------------------------------------------ #
# Date       | Name                     | BC   | Pass/Fail | Mutation                                                #
# ------------------------------------------------------------------------------------------------------------------ #
# 2026-04-15 | Sample                   | 100% | 65/0      | 136/136   🎉 85 🫥 0  ⏰ 25  🤔 0  🙁 13  🔇 0  🧙 0  #
# ------------------------------------------------------------------------------------------------------------------ #
######################################################################################################################

from django.test import SimpleTestCase

import api.filters as api_filters


class CoreWhiteBoxTests(SimpleTestCase):
    def test_child_field_filter_meta_fields(self):
        self.assertIn("child", api_filters.ChildFieldFilter.Meta.fields)

    def test_diaper_change_filter_meta_fields(self):
        fields = api_filters.DiaperChangeFilter.Meta.fields
        for name in ["wet", "solid", "color", "amount"]:
            self.assertIn(name, fields)

    def test_feeding_filter_meta_fields(self):
        fields = api_filters.FeedingFilter.Meta.fields
        for name in ["type", "method"]:
            self.assertIn(name, fields)
