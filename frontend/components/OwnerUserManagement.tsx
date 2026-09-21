'use client';

import { useEffect, useState } from 'react';
import { CheckCircle2, RefreshCw, ShieldCheck, UserX, RotateCcw, Trash2, KeyRound } from 'lucide-react';

type User = {
  user_id: string;
  full_name: string;
  email: string;
  role: string;
  status: string;
  created_at?: string;
  approved_at?: string;
  last_login?: string;
};

export default function OwnerUserManagement({ api, token, ownerUserId }: { api: string; token: string; ownerUserId: string }) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const headers = { Authorization: `Bearer ${token}` };

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const r = await fetch(`${api}/api/admin/users`, { headers });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || 'Could not load users.');
      setUsers(j.items || []);
    } catch (e: any) {
      setError(e?.message || 'Could not load users.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const action = async (userId: string, kind: 'suspend' | 'reactivate' | 'delete' | 'revoke') => {
    if (userId === ownerUserId && kind !== 'revoke') {
      setError('The permanent owner cannot be suspended, reactivated through admin controls, or deleted.');
      return;
    }
    const labels: Record<string, string> = {
      suspend: 'Suspend this user?',
      reactivate: 'Reactivate this user?',
      delete: 'Delete this user permanently?',
      revoke: 'Revoke all active sessions for this user?'
    };
    if (!window.confirm(labels[kind])) return;

    const path = kind === 'revoke'
      ? `/api/admin/users/${encodeURIComponent(userId)}/sessions/revoke`
      : `/api/admin/users/${encodeURIComponent(userId)}/${kind}`;

    try {
      setError('');
      const r = await fetch(`${api}${kind === 'delete' ? path : path}`, {
        method: kind === 'delete' ? 'DELETE' : 'POST',
        headers
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || 'Action failed.');
      setMessage(j.message || `${kind} completed successfully.`);
      await load();
    } catch (e: any) {
      setError(e?.message || 'Action failed.');
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Owner administration</div>
          <h1>User management.</h1>
          <p>Manage centralized accounts and sessions across every device.</p>
        </div>
        <button className="outline-btn" onClick={load} disabled={loading}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="dataset-note">
        <ShieldCheck size={16} /> Permanent owner protection is enabled for {ownerUserId}.
      </div>

      {message && <div className="success-box"><CheckCircle2 size={17} />{message}</div>}
      {error && <div className="error-box">{error}</div>}

      <div className="jobs-table">
        <div className="jobs-table-head">
          <span>User</span><span>Role</span><span>Status</span><span>Last login</span><span>Actions</span>
        </div>
        {loading ? <div className="dataset-note">Loading users…</div> : users.map((u) => {
          const owner = u.role.toLowerCase() === 'owner' || u.user_id === ownerUserId;
          return (
            <div className="jobs-table-row" key={u.user_id}>
              <div>
                <strong>{u.full_name}</strong>
                <small>{u.user_id} · {u.email}</small>
              </div>
              <span className="status completed">{u.role}</span>
              <span className={`status ${u.status === 'active' ? 'completed' : 'failed'}`}>{u.status}</span>
              <span>{u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}</span>
              <div className="evidence-actions">
                {owner ? (
                  <span className="status completed"><ShieldCheck size={13} /> Protected</span>
                ) : (
                  <>
                    {u.status === 'suspended'
                      ? <button onClick={() => action(u.user_id, 'reactivate')}><RotateCcw size={13} /> Reactivate</button>
                      : <button onClick={() => action(u.user_id, 'suspend')}><UserX size={13} /> Suspend</button>}
                    <button onClick={() => action(u.user_id, 'revoke')}><KeyRound size={13} /> Revoke sessions</button>
                    <button onClick={() => action(u.user_id, 'delete')}><Trash2 size={13} /> Delete</button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
