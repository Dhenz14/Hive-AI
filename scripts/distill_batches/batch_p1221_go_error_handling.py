"""
Go language training pairs - error handling (wrapping, custom errors, sentinel errors, errors.Is/As)
"""

pairs = [
    {
        "instruction": r'''<think>
The user wants to understand Go error wrapping with fmt.Errorf and %w. This was introduced in Go 1.13 and is now the standard way to add context to errors while preserving the original error for inspection. The key insight is that %w creates a chain of errors that can be unwrapped, while %v just formats the string and loses the original error. I should show a practical example with a multi-layer application where errors bubble up through layers with added context.
</think>
Explain Go error wrapping with fmt.Errorf %w and show how to build an error chain across multiple layers of an application.''',
        "output": r'''Error wrapping with `%w` creates inspectable error chains while adding context at each layer:

```go
package main

import (
	"errors"
	"fmt"
	"os"
)

// --- Data layer ---

func readConfig(path string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		// %w wraps the original error -- it can be unwrapped later
		return nil, fmt.Errorf("readConfig(%s): %w", path, err)
	}
	return data, nil
}

// --- Service layer ---

type Config struct {
	DSN string
}

func loadConfig(path string) (*Config, error) {
	data, err := readConfig(path)
	if err != nil {
		// Each layer adds context while preserving the chain
		return nil, fmt.Errorf("loadConfig: %w", err)
	}
	if len(data) == 0 {
		return nil, fmt.Errorf("loadConfig: empty config file")
	}
	return &Config{DSN: string(data)}, nil
}

// --- Application layer ---

func initApp() error {
	_, err := loadConfig("/etc/app/config.yaml")
	if err != nil {
		return fmt.Errorf("initApp: %w", err)
	}
	return nil
}

func main() {
	err := initApp()
	if err == nil {
		return
	}

	// Full chain is visible in the message
	fmt.Println("Error:", err)
	// Output: initApp: loadConfig: readConfig(/etc/app/config.yaml): open ...: no such file

	// errors.Is walks the chain to find a match
	if errors.Is(err, os.ErrNotExist) {
		fmt.Println("File does not exist -- using defaults")
	}

	// errors.Unwrap peels one layer
	inner := errors.Unwrap(err)
	fmt.Println("Unwrapped:", inner)

	// WRONG: using %v instead of %w loses the chain
	// return fmt.Errorf("initApp: %v", err)  // errors.Is would fail
}
```

Rules of thumb:
- Use `%w` when callers might need to inspect the underlying error
- Use `%v` when you want to hide internal details from callers (encapsulation)
- Always add enough context to locate the failure without a stack trace
- Wrap once per layer -- do not wrap and log at the same level'''
    },
    {
        "instruction": r'''Show me how to define custom error types in Go using the error interface, and how to use errors.As to extract them.''',
        "output": r'''Custom error types carry structured data beyond a string message. Use `errors.As` to extract them from a wrapped chain:

```go
package main

import (
	"errors"
	"fmt"
	"net/http"
)

// Custom error type -- implements the error interface
type APIError struct {
	Code    int
	Message string
	Detail  string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("API error %d: %s", e.Code, e.Message)
}

// Wrap an inner error for chaining
type ValidationError struct {
	Field   string
	Message string
	Err     error // underlying cause
}

func (e *ValidationError) Error() string {
	return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}

// Unwrap lets errors.Is and errors.As traverse the chain
func (e *ValidationError) Unwrap() error {
	return e.Err
}

// --- Service functions ---

func validateAge(age int) error {
	if age < 0 || age > 150 {
		return &ValidationError{
			Field:   "age",
			Message: "must be between 0 and 150",
			Err: &APIError{
				Code:    http.StatusBadRequest,
				Message: "invalid input",
			},
		}
	}
	return nil
}

func processRequest(age int) error {
	if err := validateAge(age); err != nil {
		return fmt.Errorf("processRequest: %w", err)
	}
	return nil
}

func main() {
	err := processRequest(-5)
	if err == nil {
		return
	}

	fmt.Println(err)

	// errors.As extracts the first matching type in the chain
	var valErr *ValidationError
	if errors.As(err, &valErr) {
		fmt.Printf("Field: %s, Message: %s\n", valErr.Field, valErr.Message)
	}

	// Can also extract the nested APIError
	var apiErr *APIError
	if errors.As(err, &apiErr) {
		fmt.Printf("HTTP code: %d\n", apiErr.Code)
	}

	// errors.Is checks identity, errors.As checks type
	// Use Is for sentinel values, As for structured errors
}
```

Design guidelines:
- Implement `Unwrap() error` if your custom error wraps another error
- Use pointer receivers (`*APIError`) so errors.As works correctly
- The target for errors.As must be a pointer to the error type pointer
- Keep custom error types in the package that defines the domain'''
    },
    {
        "instruction": r'''What are sentinel errors in Go and when should I use them vs custom error types?''',
        "output": r'''Sentinel errors are package-level variables that represent specific error conditions. They are compared by identity using `errors.Is`:

```go
package main

import (
	"errors"
	"fmt"
)

// --- Sentinel errors (package-level) ---
var (
	ErrNotFound     = errors.New("not found")
	ErrUnauthorized = errors.New("unauthorized")
	ErrConflict     = errors.New("resource conflict")
)

// --- Repository layer ---

type User struct {
	ID   int
	Name string
}

var users = map[int]User{
	1: {ID: 1, Name: "Alice"},
}

func FindUser(id int) (User, error) {
	u, ok := users[id]
	if !ok {
		// Wrap the sentinel with context
		return User{}, fmt.Errorf("FindUser(id=%d): %w", id, ErrNotFound)
	}
	return u, nil
}

func DeleteUser(id int, callerID int) error {
	if callerID != 1 {
		return fmt.Errorf("DeleteUser: %w", ErrUnauthorized)
	}
	if _, ok := users[id]; !ok {
		return fmt.Errorf("DeleteUser(id=%d): %w", id, ErrNotFound)
	}
	delete(users, id)
	return nil
}

// --- Handler layer ---

func handleDelete(userID, callerID int) {
	err := DeleteUser(userID, callerID)
	if err == nil {
		fmt.Println("deleted successfully")
		return
	}

	// Switch on sentinel errors to determine response
	switch {
	case errors.Is(err, ErrNotFound):
		fmt.Println("404:", err)
	case errors.Is(err, ErrUnauthorized):
		fmt.Println("403:", err)
	case errors.Is(err, ErrConflict):
		fmt.Println("409:", err)
	default:
		fmt.Println("500:", err)
	}
}

func main() {
	handleDelete(99, 1) // 404
	handleDelete(1, 99) // 403
	handleDelete(1, 1)  // success
}
```

When to use which:
- Sentinel errors: simple conditions callers need to branch on (not found, unauthorized, EOF)
- Custom error types: when callers need structured data (field name, HTTP code, retry-after)

Sentinel error rules:
- Name them ErrXxx by convention
- Declare with errors.New, not fmt.Errorf
- They are part of your API -- treat them as stable contracts
- Always wrap with %w when adding context so errors.Is still works
- Never compare with == directly; always use errors.Is (handles wrapping)'''
    },
    {
        "instruction": r'''<think>
The user wants to see multi-error handling in Go. Since Go 1.20, errors.Join was added which creates an error that wraps multiple errors, and both errors.Is and errors.As traverse all of them. Before 1.20 people used libraries like hashicorp/go-multierror. I should show the stdlib approach with errors.Join and also the Unwrap() []error interface for custom multi-errors.
</think>
How do I handle multiple errors in Go? Show me errors.Join and how to create custom multi-error types.''',
        "output": r'''Go 1.20 added `errors.Join` for combining multiple errors. Both `errors.Is` and `errors.As` traverse all wrapped errors:

```go
package main

import (
	"errors"
	"fmt"
	"os"
	"strings"
)

// --- Using errors.Join (Go 1.20+) ---

func validateForm(name, email string, age int) error {
	var errs []error

	if strings.TrimSpace(name) == "" {
		errs = append(errs, fmt.Errorf("name: required"))
	}
	if !strings.Contains(email, "@") {
		errs = append(errs, fmt.Errorf("email: invalid format"))
	}
	if age < 18 {
		errs = append(errs, fmt.Errorf("age: must be 18 or older"))
	}

	// Join returns nil if errs is empty -- safe to call always
	return errors.Join(errs...)
}

// --- Custom multi-error with Unwrap() []error ---

type CleanupError struct {
	Errors []error
}

func (e *CleanupError) Error() string {
	msgs := make([]string, len(e.Errors))
	for i, err := range e.Errors {
		msgs[i] = err.Error()
	}
	return fmt.Sprintf("%d cleanup failures: %s",
		len(e.Errors), strings.Join(msgs, "; "))
}

// Unwrap returns []error -- Go 1.20 multi-unwrap interface
func (e *CleanupError) Unwrap() []error {
	return e.Errors
}

func cleanup() error {
	var errs []error

	// Simulate closing multiple resources
	if err := os.Remove("/tmp/lock.pid"); err != nil {
		errs = append(errs, fmt.Errorf("remove lock: %w", err))
	}
	if err := os.Remove("/tmp/cache.dat"); err != nil {
		errs = append(errs, fmt.Errorf("remove cache: %w", err))
	}

	if len(errs) > 0 {
		return &CleanupError{Errors: errs}
	}
	return nil
}

func main() {
	// Validation example
	err := validateForm("", "bad-email", 15)
	if err != nil {
		fmt.Println("Validation errors:")
		fmt.Println(err)
	}

	// Cleanup example -- errors.Is traverses ALL wrapped errors
	err = cleanup()
	if err != nil {
		fmt.Println("\nCleanup errors:", err)

		// errors.Is checks every error in the tree
		if errors.Is(err, os.ErrNotExist) {
			fmt.Println("Some files were already gone")
		}
	}
}
```

Key points:
- errors.Join returns nil when given no errors -- safe in defer/cleanup patterns
- Implement `Unwrap() []error` (not `Unwrap() error`) for custom multi-errors
- errors.Is and errors.As traverse the entire error tree, not just linear chains
- Collect errors in a slice, then join at the end -- never ignore partial failures'''
    },
    {
        "instruction": r'''Show me idiomatic Go error handling patterns for a function that must clean up resources even when errors occur (defer + named returns).''',
        "output": r'''Use named return values with defer to handle cleanup errors without losing the original error:

```go
package main

import (
	"database/sql"
	"fmt"
	"io"
	"os"
)

// Pattern 1: defer with named error return
func copyFile(dst, src string) (err error) {
	srcFile, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("open source: %w", err)
	}
	defer func() {
		closeErr := srcFile.Close()
		if err == nil {
			err = closeErr // only overwrite if no prior error
		}
	}()

	dstFile, err := os.Create(dst)
	if err != nil {
		return fmt.Errorf("create dest: %w", err)
	}
	defer func() {
		closeErr := dstFile.Close()
		if err == nil {
			err = closeErr
		}
	}()

	_, err = io.Copy(dstFile, srcFile)
	if err != nil {
		return fmt.Errorf("copy data: %w", err)
	}

	// Explicitly sync to catch write errors before close
	return dstFile.Sync()
}

// Pattern 2: transaction with rollback on error
func transferFunds(db *sql.DB, from, to int, amount float64) (err error) {
	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() {
		if err != nil {
			// Rollback on any error; log rollback failure
			if rbErr := tx.Rollback(); rbErr != nil {
				err = fmt.Errorf("%w (rollback also failed: %v)", err, rbErr)
			}
		}
	}()

	_, err = tx.Exec("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, from)
	if err != nil {
		return fmt.Errorf("debit: %w", err)
	}

	_, err = tx.Exec("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, to)
	if err != nil {
		return fmt.Errorf("credit: %w", err)
	}

	if err = tx.Commit(); err != nil {
		return fmt.Errorf("commit: %w", err)
	}
	return nil
}

func main() {
	err := copyFile("/tmp/dst.txt", "/tmp/src.txt")
	if err != nil {
		fmt.Println("copy failed:", err)
	}
}
```

Rules for defer + error cleanup:
- Use named return `(err error)` so deferred closures can read and modify the return value
- In the defer, only overwrite err if it is nil -- never lose the original error
- For transactions, defer rollback and only skip it when commit succeeds
- Call Sync() before Close() on files to catch write errors
- Defers run LIFO -- resources are cleaned up in reverse order of acquisition'''
    },
]
