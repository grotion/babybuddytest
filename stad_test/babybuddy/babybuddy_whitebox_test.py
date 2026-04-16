######################################################################################################################
# babybuddy whitebox test                                                                                            #
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

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

import api.serializers as api_serializers


class BabyBuddyWhiteBoxTests(SimpleTestCase):
    def test_profile_serializer_reads_api_key_from_instance(self):
        serializer = api_serializers.ProfileSerializer()
        serializer.instance = SimpleNamespace(
            api_key=lambda: SimpleNamespace(key="generated-key")
        )
        self.assertEqual(serializer.get_api_key(None), "generated-key")

    def test_user_serializer_declares_read_only_fields(self):
        fields = api_serializers.UserSerializer.Meta.fields
        extra_kwargs = api_serializers.UserSerializer.Meta.extra_kwargs
        for field in fields:
            self.assertTrue(extra_kwargs[field]["read_only"])
