import { createHash } from "crypto";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import * as argon2 from "argon2";

const client = DynamoDBDocumentClient.from(
  new DynamoDBClient({ region: process.env.AWS_REGION || "us-east-1" }),
);

export type PortalUser = {
  username: string;
  customer_id: string;
  password_hash: string;
  enabled?: boolean;
  email?: string;
};

export async function getPortalUser(username: string): Promise<PortalUser | null> {
  const table = process.env.PORTAL_USERS_TABLE || "itah-portal-users";
  const result = await client.send(
    new GetCommand({
      TableName: table,
      Key: { username },
    }),
  );
  return (result.Item as PortalUser | undefined) ?? null;
}

export type SparkStatus = {
  id?: string;
  online?: boolean;
  origin_base_url?: string;
  updated_at?: string;
};

/** Admin "Go online / offline" flag in DynamoDB (not tunnel/Mac reachability). */
export async function getSparkStatus(): Promise<SparkStatus> {
  const table = process.env.SPARK_STATUS_TABLE || "itah-spark-status";
  const result = await client.send(
    new GetCommand({
      TableName: table,
      Key: { id: "singleton" },
    }),
  );
  return (result.Item as SparkStatus | undefined) ?? { id: "singleton", online: false };
}

export type PortalInvite = {
  token_hash: string;
  email: string;
  customer_id: string;
  status: string;
  expires_at: string;
  expires_epoch?: number;
  used_at?: string;
};

function invitesTable(): string {
  return process.env.PORTAL_INVITES_TABLE || "itah-portal-invites";
}

function usersTable(): string {
  return process.env.PORTAL_USERS_TABLE || "itah-portal-users";
}

export function hashInviteToken(rawToken: string): string {
  return createHash("sha256").update(rawToken, "utf8").digest("hex");
}

export async function getPortalInvite(rawToken: string): Promise<PortalInvite | null> {
  const result = await client.send(
    new GetCommand({
      TableName: invitesTable(),
      Key: { token_hash: hashInviteToken(rawToken) },
    }),
  );
  return (result.Item as PortalInvite | undefined) ?? null;
}

export function inviteIsAcceptable(invite: PortalInvite | null): {
  ok: boolean;
  error?: string;
  invite?: PortalInvite;
} {
  if (!invite) return { ok: false, error: "Invite not found" };
  if (invite.status === "used") return { ok: false, error: "Invite already used" };
  if (invite.status === "revoked") return { ok: false, error: "Invite revoked" };
  if (invite.status !== "pending") return { ok: false, error: "Invite unavailable" };
  const expiresMs = Date.parse(invite.expires_at);
  if (!Number.isFinite(expiresMs) || expiresMs < Date.now()) {
    return { ok: false, error: "Invite expired" };
  }
  return { ok: true, invite };
}

export async function acceptPortalInvite(opts: {
  rawToken: string;
  username: string;
  password: string;
}): Promise<{ username: string; customer_id: string; email: string }> {
  const username = opts.username.trim();
  const password = opts.password;
  if (!username || username.length < 3) {
    throw new Error("Username must be at least 3 characters");
  }
  if (!/^[a-zA-Z0-9._-]+$/.test(username)) {
    throw new Error("Username may only contain letters, numbers, . _ -");
  }
  if (!password || password.length < 8) {
    throw new Error("Password must be at least 8 characters");
  }

  const check = inviteIsAcceptable(await getPortalInvite(opts.rawToken));
  if (!check.ok || !check.invite) {
    throw new Error(check.error || "Invalid invite");
  }
  const invite = check.invite;

  const existing = await getPortalUser(username);
  if (existing) {
    throw new Error("Username already taken");
  }

  const now = new Date().toISOString();
  const password_hash = await argon2.hash(password);

  await client.send(
    new PutCommand({
      TableName: usersTable(),
      Item: {
        username,
        customer_id: invite.customer_id,
        password_hash,
        email: invite.email,
        enabled: true,
        created_at: now,
        updated_at: now,
      },
      ConditionExpression: "attribute_not_exists(username)",
    }),
  );

  try {
    await client.send(
      new UpdateCommand({
        TableName: invitesTable(),
        Key: { token_hash: invite.token_hash },
        UpdateExpression: "SET #s = :used, used_at = :u, used_by = :ub",
        ConditionExpression: "#s = :pending",
        ExpressionAttributeNames: { "#s": "status" },
        ExpressionAttributeValues: {
          ":used": "used",
          ":pending": "pending",
          ":u": now,
          ":ub": username,
        },
      }),
    );
  } catch {
    // Best-effort rollback if invite was raced; leave orphan user disabled.
    await client.send(
      new UpdateCommand({
        TableName: usersTable(),
        Key: { username },
        UpdateExpression: "SET enabled = :f",
        ExpressionAttributeValues: { ":f": false },
      }),
    );
    throw new Error("Invite was already used; try a new invite");
  }

  return { username, customer_id: invite.customer_id, email: invite.email };
}
