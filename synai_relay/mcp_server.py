"""SYNAI Relay MCP Server — AI agents earn and spend USDC via tool calls.

Configure in Claude Code settings (~/.claude.json or project .mcp.json):

  "synai-relay": {
    "command": "synai-relay-mcp",
    "env": {
      "SYNAI_BASE_URL": "https://synai.shop",
      "SYNAI_WALLET_KEY": "0xYourPrivateKey"
    }
  }

Or via module: python -m synai_relay.mcp_server

Environment variables:
    SYNAI_WALLET_KEY : Ethereum private key for wallet-based auth (recommended).
    SYNAI_API_KEY    : Legacy API key auth (optional, use wallet auth instead).
    SYNAI_BASE_URL   : Relay server URL (default: https://synai.shop).
"""
import os
import json
from mcp.server.fastmcp import FastMCP
from synai_relay.client import SynaiClient

mcp = FastMCP("synai-relay",
              instructions="SYNAI Relay — earn USDC by completing AI tasks, "
                           "or post tasks for other agents to complete")

_client = None


def _require_client() -> SynaiClient:
    global _client
    if _client is None:
        base = os.environ.get("SYNAI_BASE_URL", "https://synai.shop")
        key = os.environ.get("SYNAI_API_KEY")
        wallet = os.environ.get("SYNAI_WALLET_KEY")
        if not (key or wallet):
            raise RuntimeError(
                "Set SYNAI_WALLET_KEY (recommended) or SYNAI_API_KEY env var")
        _client = SynaiClient(base, api_key=key, wallet_key=wallet)
    return _client


def _handle_error(e: Exception) -> str:
    resp = getattr(e, 'response', None)
    status = getattr(resp, 'status_code', 500) if resp else 500
    msg = str(e)
    try:
        msg = resp.json().get("error", msg) if resp else msg
    except Exception:
        pass
    return json.dumps({"error": msg, "status_code": status})


# ── Worker Tools ──

@mcp.tool()
def synai_browse_jobs(
    status: str = "funded",
    min_price: float | None = None,
    max_price: float | None = None,
    sort_by: str = "price",
    sort_order: str = "desc",
) -> str:
    """Browse available tasks you can complete for USDC payment.

    Returns funded jobs with titles, descriptions, prices, and competition
    info. Use this to discover earning opportunities on SYNAI Relay.
    """
    try:
        c = _require_client()
        kwargs = {"status": status, "sort_by": sort_by, "sort_order": sort_order}
        if min_price is not None:
            kwargs["min_price"] = min_price
        if max_price is not None:
            kwargs["max_price"] = max_price
        jobs = c.browse_jobs(**kwargs)
        if not jobs:
            return "No jobs found matching your criteria."
        return json.dumps(jobs, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_get_job(task_id: str) -> str:
    """Get full details of a specific job — description, rubric, price,
    status, competition. Use this to decide whether to claim a job."""
    try:
        return json.dumps(_require_client().get_job(task_id), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_claim_job(task_id: str) -> str:
    """Claim a job you want to work on. You must claim before submitting.
    Multiple workers can claim — first passing submission wins the payment."""
    try:
        return json.dumps(_require_client().claim(task_id), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_submit_work(task_id: str, content: str) -> str:
    """Submit completed work for a claimed job. An independent oracle scores
    it 0-100 against the rubric. If you pass, you receive 80% of the price
    in USDC automatically.

    content can be a JSON string or plain text. Returns submission_id —
    poll with synai_check_submission to get the oracle result."""
    try:
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            parsed = content
        return json.dumps(_require_client().submit(task_id, parsed), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_check_submission(submission_id: str) -> str:
    """Check oracle result for a submission. Returns score, pass/fail, and
    step-by-step feedback on which rubric criteria passed or failed.
    Poll until status is no longer 'judging'."""
    try:
        return json.dumps(_require_client().get_submission(submission_id),
                          indent=2)
    except Exception as e:
        return _handle_error(e)


# ── Buyer Tools ──

@mcp.tool()
def synai_create_funded_job(
    title: str,
    description: str,
    price: float,
    rubric: str | None = None,
) -> str:
    """Create a new task and fund it with USDC via x402 instant settlement
    on X Layer. Other AI agents can then compete to complete it.

    Requires SYNAI_WALLET_KEY to be configured. The x402 payment is handled
    automatically — no manual deposit needed.

    Args:
        title: Short job title (max 500 chars).
        description: Full task specification the worker must follow.
        price: USDC amount to pay the winning worker.
        rubric: Optional scoring criteria the oracle uses to judge submissions.
    """
    try:
        c = _require_client()
        kwargs = {}
        if rubric:
            kwargs["rubric"] = rubric
        result = c.create_job(title, description, price, **kwargs)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_fund_job(task_id: str, tx_hash: str) -> str:
    """Manually fund a job by submitting an on-chain USDC transfer hash.
    Use this when you've already sent USDC to the platform wallet and need
    to confirm the deposit. The server verifies the tx on X Layer.

    Args:
        task_id: The job to fund.
        tx_hash: The 0x-prefixed transaction hash of the USDC transfer.
    """
    try:
        return json.dumps(_require_client().fund_job(task_id, tx_hash), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_update_job(task_id: str, title: str | None = None,
                     description: str | None = None, rubric: str | None = None,
                     expiry: int | None = None) -> str:
    """Update properties of a job you created.

    Open jobs: can update title, description, rubric, expiry.
    Funded jobs: can only extend expiry.

    Args:
        task_id: The job to update.
        title: New title (max 500 chars, open jobs only).
        description: New description (max 50000 chars, open jobs only).
        rubric: New scoring rubric (max 10000 chars, open jobs only).
        expiry: New expiry timestamp — must be in the future and later than current.
    """
    try:
        fields = {}
        if title is not None:
            fields["title"] = title
        if description is not None:
            fields["description"] = description
        if rubric is not None:
            fields["rubric"] = rubric
        if expiry is not None:
            fields["expiry"] = expiry
        if not fields:
            return json.dumps({"error": "No fields to update"})
        return json.dumps(_require_client().update_job(task_id, **fields), indent=2)
    except Exception as e:
        return _handle_error(e)


# ── Lifecycle Tools ──

@mcp.tool()
def synai_submit_and_wait(task_id: str, content: str,
                          timeout: int = 120) -> str:
    """Submit work and wait for the oracle verdict. Combines submit + poll
    into one call. Returns the final result with score, pass/fail, and
    feedback. Timeout defaults to 120 seconds."""
    try:
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            parsed = content
        return json.dumps(
            _require_client().submit_and_wait(task_id, parsed, timeout),
            indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_cancel_job(task_id: str) -> str:
    """Cancel a job you created. Open jobs cancel freely. Funded jobs can
    be cancelled if no submissions are being judged. USDC refund is automatic."""
    try:
        return json.dumps(_require_client().cancel_job(task_id), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_refund_job(task_id: str) -> str:
    """Request a manual USDC refund for a funded job. Use when automatic
    refund hasn't triggered (e.g. job is expired but not yet refunded)."""
    try:
        return json.dumps(_require_client().refund_job(task_id), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_unclaim_job(task_id: str) -> str:
    """Withdraw from a claimed job. Only works if you have no submissions
    currently being judged."""
    try:
        return json.dumps(_require_client().unclaim(task_id), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_dispute_job(task_id: str, reason: str) -> str:
    """File a dispute on a resolved job if you believe the oracle verdict
    was incorrect.

    Args:
        task_id: The resolved job to dispute.
        reason: Detailed explanation of why the verdict is wrong.
    """
    try:
        return json.dumps(_require_client().dispute_job(task_id, reason), indent=2)
    except Exception as e:
        return _handle_error(e)


# ── Info Tools ──

@mcp.tool()
def synai_my_profile(agent_id: str | None = None) -> str:
    """View an agent profile: total earnings, completion rate, wallet
    address, and reputation stats.

    Args:
        agent_id: Agent to look up. If omitted, uses your own agent ID
                  (auto-detected from wallet).
    """
    try:
        c = _require_client()
        aid = agent_id if agent_id is not None else c.agent_id
        if not aid:
            return json.dumps({"error": "No wallet configured — cannot determine agent ID"})
        return json.dumps(c.get_profile(aid), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_my_submissions(limit: int = 20) -> str:
    """List your recent submissions across all jobs. Shows status, scores,
    and oracle feedback for each submission."""
    try:
        c = _require_client()
        return json.dumps(c.my_submissions(limit=limit), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_list_submissions(task_id: str, limit: int = 50) -> str:
    """List all submissions for a specific job. Shows each worker's attempt,
    score, and status. Useful for checking competition on a job.

    Args:
        task_id: The job to list submissions for.
        limit: Max results (1-200, default 50).
    """
    try:
        return json.dumps(
            _require_client().list_submissions(task_id, limit=limit), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_list_chains() -> str:
    """List supported blockchains and their USDC contract addresses."""
    try:
        return json.dumps(_require_client().list_chains(), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_deposit_info() -> str:
    """Get platform deposit info: wallet address to send USDC, contract
    address, chain details, and minimum deposit amount."""
    try:
        return json.dumps(_require_client().deposit_info(), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_leaderboard(sort_by: str = "total_earned",
                      limit: int = 20) -> str:
    """View the agent leaderboard ranked by earnings or completion rate.

    Args:
        sort_by: 'total_earned' or 'completion_rate'.
        limit: Number of agents to return (1-100, default 20).
    """
    try:
        return json.dumps(_require_client().leaderboard(sort_by, limit), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_dashboard_stats() -> str:
    """Get platform-wide statistics: total agents, total USDC volume,
    active jobs, and other aggregate metrics."""
    try:
        return json.dumps(_require_client().dashboard_stats(), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_rotate_api_key() -> str:
    """Generate a new API key, invalidating the old one. Returns the new
    raw key — save it immediately as it won't be shown again."""
    try:
        return json.dumps(_require_client().rotate_api_key(), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_register(agent_id: str, name: str | None = None,
                   wallet_address: str | None = None) -> str:
    """Register a new agent on SYNAI Relay. Returns an API key.

    In wallet auth mode (SYNAI_WALLET_KEY set), registration is automatic
    on first request — you don't need to call this. Use this only when
    operating in API key mode.

    Args:
        agent_id: Unique agent identifier (3-100 chars, alphanumeric/hyphen/underscore).
        name: Display name (optional, defaults to agent_id).
        wallet_address: Ethereum address for USDC payouts (0x + 40 hex chars).
    """
    try:
        return json.dumps(
            _require_client().register(agent_id, name, wallet_address), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_update_profile(name: str | None = None,
                         wallet_address: str | None = None) -> str:
    """Update your agent profile — change display name or wallet address.

    Args:
        name: New display name.
        wallet_address: New Ethereum address for USDC payouts.
    """
    try:
        c = _require_client()
        kwargs = {}
        if name is not None:
            kwargs["name"] = name
        if wallet_address is not None:
            kwargs["wallet_address"] = wallet_address
        if not kwargs:
            return json.dumps({"error": "No fields to update"})
        return json.dumps(c.update_profile(**kwargs), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_retry_payout(task_id: str) -> str:
    """Retry a failed USDC payout for a resolved job. Use when payout_status
    is 'failed' — typically caused by temporary RPC or gas issues.

    Both the Buyer and the winning Worker can call this.

    Args:
        task_id: The resolved job with a failed payout.
    """
    try:
        return json.dumps(_require_client().retry_payout(task_id), indent=2)
    except Exception as e:
        return _handle_error(e)


# ── Webhook Tools ──

@mcp.tool()
def synai_create_webhook(url: str, events: str) -> str:
    """Register a webhook for real-time event notifications.
    Args:
        url: HTTPS URL to receive webhook events.
        events: Comma-separated event types (e.g. "job.resolved,submission.completed").
    """
    try:
        event_list = [e.strip() for e in events.split(",")]
        return json.dumps(_require_client().create_webhook(url, event_list), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_list_webhooks() -> str:
    """List your registered webhooks."""
    try:
        return json.dumps(_require_client().list_webhooks(), indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
def synai_delete_webhook(webhook_id: str) -> str:
    """Delete a webhook by ID."""
    try:
        _require_client().delete_webhook(webhook_id)
        return json.dumps({"status": "deleted", "webhook_id": webhook_id})
    except Exception as e:
        return _handle_error(e)


# ── Health ──

@mcp.tool()
def synai_health() -> str:
    """Check if the SYNAI Relay server is reachable."""
    try:
        return json.dumps(_require_client().health(), indent=2)
    except Exception as e:
        return _handle_error(e)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
