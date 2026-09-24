import { useEffect, useState } from 'react'
import {
  apiGet,
  apiPost,
  apiPatch,
  apiDelete,
} from '../api/client'
import {
  CheckCircle2,
  Loader2,
  Minus,
  Plus,
  UserPlus,
  Users,
} from 'lucide-react'

import PageHeader from '../components/layout/PageHeader'
import Card from '../components/common/Card'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'


function UserManagement() {
  const [users, setUsers] = useState([])
  const [permissions, setPermissions] = useState([])
  const [roles, setRoles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [updating, setUpdating] = useState(null)
  const [message, setMessage] = useState(null)
  const [creatingUser, setCreatingUser] = useState(false)

  const currentUser = (() => {
    try {
      const storedUser = sessionStorage.getItem('chat_user')

      return storedUser
        ? JSON.parse(storedUser)
        : null
    } catch {
      return null
    }
  })()

  const currentUserRoles = Array.isArray(currentUser?.roles)
    ? currentUser.roles
    : []

  const isSuperadmin =
    currentUserRoles.includes('superadmin')

  const allowedRoles = roles.filter((role) => {
    if (isSuperadmin) {
      return (
        role.role_name === 'admin' ||
        role.role_name === 'user'
      )
    }

    return role.role_name === 'user'
  })

  const [newUser, setNewUser] = useState({
    username: '',
    password: '',
    companies: [],
    role_name: '',
  })


  async function loadAdminData(showLoader = true) {
    if (showLoader) {
      setLoading(true)
    }

    setError(null)

    try {
      const [
        usersResult,
        permissionsResult,
        rolesResult,
      ] = await Promise.all([
        apiGet('/admin/users'),
        apiGet('/admin/permissions'),
        apiGet('/admin/roles'),
      ])

      setUsers(usersResult)
      setPermissions(permissionsResult)
      setRoles(rolesResult)
    } catch (err) {
      setError(err.message)
    } finally {
      if (showLoader) {
        setLoading(false)
      }
    }
  }


  useEffect(() => {
    loadAdminData()
  }, [])


  function handleNewUserChange(event) {
    const { name, value } = event.target

    setNewUser((current) => ({
      ...current,
      [name]: value,
    }))
  }


  async function handleCreateUser(event) {
    event.preventDefault()

    setCreatingUser(true)
    setError(null)
    setMessage(null)

    try {

      await apiPost(
        '/admin/users',
        {
          username: newUser.username.trim(),
          password: newUser.password,
          companies: newUser.companies,
          role_name: newUser.role_name,
        }
      )

      setMessage(
        `User ${newUser.username} created successfully.`
      )

      setNewUser({
        username: '',
        password: '',
        companies: [],
        role_name: '',
      })

      await loadAdminData()
    } catch (err) {
      setError(err.message)
    } finally {
      setCreatingUser(false)
    }
  }


  async function handleAssign(userId, permissionCode) {
    const operationKey =
      `${userId}-${permissionCode}`

    setUpdating(operationKey)
    setError(null)
    setMessage(null)

    try {
      await apiPost(
        `/admin/users/${encodeURIComponent(userId)}/permissions`,
        {
          permission_code: permissionCode,
        }
      )

      setMessage(
        `${permissionCode} permission assigned successfully.`
      )

      await loadAdminData(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setUpdating(null)
    }
  }


  async function handleRemove(userId, permissionCode) {
    const operationKey =
      `${userId}-${permissionCode}`

    setUpdating(operationKey)
    setError(null)
    setMessage(null)

    try {
      await apiDelete(
        `/admin/users/${encodeURIComponent(
          userId
        )}/permissions/${encodeURIComponent(
          permissionCode
        )}`
      )

      setMessage(
        `${permissionCode} permission removed successfully.`
      )

      await loadAdminData(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setUpdating(null)
    }
  }


  async function handleUserStatusChange(userId, isActive) {
    const operationKey = `${userId}-status`

    setUpdating(operationKey)
    setMessage(null)
    setError(null)

    try {
      const result = await apiPatch(
        `/admin/users/${encodeURIComponent(userId)}/status`,
        {
          is_active: isActive,
        }
      )

      setMessage(result.message)

      await loadAdminData(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setUpdating(null)
    }
  }


  return (
    <>
      <PageHeader
        title="User Management"
        subtitle="Create users and control which parts of Tally they can access"
      />

      {loading && <Loader />}

      {error && (
        <ErrorMessage message={error} />
      )}

      {message && (
        <div className="success-message" role="status">
          <CheckCircle2 size={18} />
          <span>{message}</span>
        </div>
      )}

      {!loading && (
        <>
          <Card
            title="Create New User"
            subtitle="New users can sign in immediately with these credentials"
          >
            <form onSubmit={handleCreateUser}>
              <div className="form-grid">
                <div className="form-field">
                  <label htmlFor="username">
                    Username
                  </label>

                  <input
                    id="username"
                    name="username"
                    type="text"
                    value={newUser.username}
                    onChange={handleNewUserChange}
                    required
                    disabled={creatingUser}
                  />
                </div>

                <div className="form-field">
                  <label htmlFor="password">
                    Password
                  </label>

                  <input
                    id="password"
                    name="password"
                    type="password"
                    value={newUser.password}
                    onChange={handleNewUserChange}
                    required
                    minLength={8}
                    autoComplete="new-password"
                    disabled={creatingUser}
                  />

                  <p className="form-hint">
                    At least 8 characters.
                  </p>
                </div>

                <div className="form-field">
                  <label htmlFor="company">
                    Company
                  </label>

                  <select
                    id="company"
                    value={newUser.companies[0] || ''}
                    onChange={(event) =>
                      setNewUser((current) => ({
                        ...current,
                        companies: event.target.value
                          ? [event.target.value]
                          : [],
                      }))
                    }
                    required
                    disabled={creatingUser}
                  >
                    <option value="">
                      Select a company
                    </option>

                    {(currentUser?.companies || []).map((company) => (
                      <option
                        key={company}
                        value={company}
                      >
                        {company}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-field">
                  <label htmlFor="role_name">
                    Role
                  </label>

                  <select
                    id="role_name"
                    name="role_name"
                    value={newUser.role_name}
                    onChange={handleNewUserChange}
                    required
                    disabled={creatingUser}
                  >
                    <option value="">
                      Select a role
                    </option>

                    {allowedRoles.map((role) => (
                      <option
                        key={role.role_id}
                        value={role.role_name}
                      >
                        {role.role_name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-actions">
                <button
                  type="submit"
                  className="btn"
                  disabled={
                    creatingUser ||
                    newUser.companies.length === 0 ||
                    !newUser.role_name
                  }
                >
                  {creatingUser ? (
                    <Loader2
                      size={16}
                      className="spin"
                    />
                  ) : (
                    <UserPlus size={16} />
                  )}

                  {creatingUser
                    ? 'Creating...'
                    : 'Create User'}
                </button>
              </div>
            </form>
          </Card>

          {!error && (
            <>
              <Card
                title="Users"
                subtitle={`${users.length} ${
                  users.length === 1
                    ? 'user'
                    : 'users'
                }`}
              >
                {users.length === 0 ? (
                  <div className="empty-state">
                    <Users
                      size={28}
                      strokeWidth={1.5}
                    />
                    <span>No users found.</span>
                  </div>
                ) : (
                  <div className="user-list">
                    {users.map((user) => (
                      <div
                        key={user.user_id}
                        className="user-row"
                      >
                        <div className="user-row-header">
                          <div className="sidebar-avatar">
                            {(user.username || 'U')
                              .trim()
                              .charAt(0)
                              .toUpperCase()}
                          </div>

                          <div className="user-row-identity">
                            <strong>
                              {user.username}
                            </strong>
                          </div>

                          <div className="tag-list">
                            <span
                              className={
                                user.is_active
                                  ? 'tag tag--accent'
                                  : 'tag'
                              }
                            >
                              {user.is_active
                                ? 'Active'
                                : 'Inactive'}
                            </span>

                            {user.roles.length > 0 ? (
                              user.roles.map((role) => (
                                <span
                                  key={role}
                                  className={
                                    role === 'admin' ||
                                    role === 'superadmin'
                                      ? 'tag tag--accent'
                                      : 'tag'
                                  }
                                >
                                  {role}
                                </span>
                              ))
                            ) : (
                              <span className="tag">
                                No role
                              </span>
                            )}

                            <button
                              type="button"
                              className={
                                user.is_active
                                  ? 'btn btn--sm btn--danger'
                                  : 'btn btn--sm btn-secondary'
                              }
                              disabled={
                                updating ===
                                `${user.user_id}-status`
                              }
                              onClick={() =>
                                handleUserStatusChange(
                                  user.user_id,
                                  !user.is_active
                                )
                              }
                            >
                              {updating ===
                              `${user.user_id}-status` ? (
                                <>
                                  <Loader2
                                    size={14}
                                    className="spin"
                                  />
                                  Updating...
                                </>
                              ) : user.is_active ? (
                                'Deactivate'
                              ) : (
                                'Activate'
                              )}
                            </button>
                          </div>
                        </div>

                        <div className="permission-grid">
                          {permissions.map((permission) => {
                            const assigned =
                              user.permissions.includes(
                                permission.permission_code
                              )

                            const operationKey =
                              `${user.user_id}-${permission.permission_code}`

                            const isUpdating =
                              updating === operationKey

                            return (
                              <div
                                key={permission.permission_id}
                                className={
                                  assigned
                                    ? 'permission-tile permission-tile--assigned'
                                    : 'permission-tile'
                                }
                              >
                                <div className="permission-tile-copy">
                                  <strong>
                                    {permission.permission_name}
                                  </strong>

                                  <span>
                                    {assigned
                                      ? 'Assigned'
                                      : 'Not assigned'}
                                  </span>
                                </div>

                                {assigned ? (
                                  <button
                                    type="button"
                                    className="btn btn--sm btn--danger"
                                    disabled={isUpdating}
                                    onClick={() =>
                                      handleRemove(
                                        user.user_id,
                                        permission.permission_code
                                      )
                                    }
                                  >
                                    {isUpdating ? (
                                      <Loader2
                                        size={14}
                                        className="spin"
                                      />
                                    ) : (
                                      <Minus size={14} />
                                    )}

                                    {isUpdating
                                      ? 'Removing...'
                                      : 'Remove'}
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    className="btn btn--sm btn-secondary"
                                    disabled={isUpdating}
                                    onClick={() =>
                                      handleAssign(
                                        user.user_id,
                                        permission.permission_code
                                      )
                                    }
                                  >
                                    {isUpdating ? (
                                      <Loader2
                                        size={14}
                                        className="spin"
                                      />
                                    ) : (
                                      <Plus size={14} />
                                    )}

                                    {isUpdating
                                      ? 'Assigning...'
                                      : 'Assign'}
                                  </button>
                                )}
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>

            </>
          )}
        </>
      )}
    </>
  )
}

export default UserManagement