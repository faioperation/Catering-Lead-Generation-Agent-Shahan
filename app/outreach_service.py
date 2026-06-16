from typing import Any, Dict, List, Optional


class OutreachService:
    def build_message(self, campaign: Dict[str, Any], lead: Dict[str, Any]) -> Dict[str, str]:
        business_name = lead.get("business_name") or "there"
        campaign_name = campaign.get("name") or "our catering service"
        offer = campaign.get("offer") or "a reliable catering solution for events, offices, and private functions"
        tone = (campaign.get("tone") or "professional").lower()
        target_audience = campaign.get("target_audience") or "local businesses and event organizers"

        subject = f"Catering support for {business_name}"

        greeting = f"Hello {business_name} team,"

        if tone == "friendly":
            body = (
                f"{greeting}\n\n"
                f"I came across {business_name} and thought this might be useful. "
                f"We are currently running the {campaign_name} campaign for {target_audience}.\n\n"
                f"The main offer is: {offer}.\n\n"
                "If you handle events, staff meals, private functions, or group orders, "
                "I would be happy to share a simple catering option that fits your needs.\n\n"
                "Would you be open to a quick conversation this week?\n\n"
                "Best regards,"
            )
        else:
            body = (
                f"{greeting}\n\n"
                f"I am reaching out because {business_name} appears to be a strong fit for our "
                f"{campaign_name} campaign, focused on {target_audience}.\n\n"
                f"Current offer: {offer}.\n\n"
                "We can support business lunches, events, staff meals, and group catering requirements "
                "with a clear, reliable outreach and fulfillment process.\n\n"
                "Would it be possible to schedule a brief call to understand whether this is relevant for your team?\n\n"
                "Regards,"
            )

        return {"subject": subject, "body": body}
